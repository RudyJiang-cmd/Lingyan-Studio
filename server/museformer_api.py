import os
import platform
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import miditoolkit
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def resolve_existing_path(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate and str(candidate) not in ("", ".") and candidate.exists():
            return candidate
    return candidates[-1]


THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
MUSEFORMER_ROOT = resolve_existing_path(
    Path(os.environ["MUSEFORMER_ROOT"]) if os.environ.get("MUSEFORMER_ROOT") else None,
    PROJECT_ROOT / "muzic" / "museformer",
    Path("/home/ubuntu/muzic/museformer"),
)
MUSECOCO_ROOT = resolve_existing_path(
    Path(os.environ["MUSECOCO_ROOT"]) if os.environ.get("MUSECOCO_ROOT") else None,
    PROJECT_ROOT / "muzic" / "musecoco" / "2-attribute2music_model",
    Path("/home/ubuntu/muzic/musecoco/2-attribute2music_model"),
)

for path in (MUSEFORMER_ROOT, MUSECOCO_ROOT):
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.append(resolved)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MelodyRequest(BaseModel):
    melody: list
    style_prompt: Optional[str] = None
    controls: Optional[Dict[str, Any]] = None


@app.get("/health")
async def health_check():
    return {
        "status": "ready" if model_loaded else "error",
        "model_loaded": model_loaded,
        "error": error_msg,
        "museformer_root": str(MUSEFORMER_ROOT),
        "musecoco_root": str(MUSECOCO_ROOT),
        "cuda_available": torch.cuda.is_available(),
        "python": platform.python_version(),
    }


TOTAL_STEPS = 16
TICKS_PER_BEAT = 480
TICKS_PER_STEP = TICKS_PER_BEAT // 4
POS_PER_STEP = 3
GENERATED_VOICES = ("alto", "tenor", "bass")
DUNHUANG_TRACK_VOICES = ("xiao", "pipa", "guqin")
PERCUSSION_VOICE = "percussion"
ALLOWED_PITCHES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
VOICE_TARGET_INTERVALS = {
    "xiao": -3,
    "pipa": -8,
    "guqin": -14,
}
VOICE_PITCH_RANGES = {
    "xiao": (6, 12),
    "pipa": (9, 13),
    "guqin": (11, 14),
}
DEFAULT_CONTROLS = {
    "texture": "dunhuang_quartet",
    "percussion": False,
}

ARRANGEMENT_PHASE_LABELS = {
    "alto": "加入高声部",
    "tenor": "加入中声部",
    "bass": "加入低声部",
    "xiao": "加入箫",
    "pipa": "加入琵琶",
    "guqin": "加入古琴",
    PERCUSSION_VOICE: "加入鼓点",
}

PITCH_TO_MIDI = {
    14: 60,
    13: 62,
    12: 64,
    11: 66,
    10: 67,
    9: 69,
    8: 71,
    7: 72,
    6: 74,
    5: 76,
    4: 78,
    3: 79,
    2: 81,
    1: 83,
    0: 84,
}


def midi_to_pitch_index(midi_pitch: int) -> int:
    best_pitch_index = 14
    best_diff = float("inf")
    for pitch_index, candidate_midi in PITCH_TO_MIDI.items():
        candidate_midi = PITCH_TO_MIDI[pitch_index]
        diff = abs(midi_pitch - candidate_midi)
        if diff < best_diff:
            best_diff = diff
            best_pitch_index = pitch_index
    return best_pitch_index


def pitch_index_to_midi(pitch_index: int) -> int:
    return PITCH_TO_MIDI[pitch_index]


def read_pitch_index(note) -> int:
    raw_pitch = int(round(note.get("pitch", note.get("midi", 14))))
    if raw_pitch in PITCH_TO_MIDI:
        return raw_pitch
    return midi_to_pitch_index(raw_pitch)


def normalize_controls(style_prompt: Optional[str], controls: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = dict(DEFAULT_CONTROLS)
    if controls:
        normalized.update({key: value for key, value in controls.items() if value is not None})
    if style_prompt:
        normalized["style_prompt"] = style_prompt
    normalized["texture"] = "dunhuang_quartet"
    normalized["percussion"] = bool(normalized.get("percussion"))
    return normalized


def controls_metadata(controls: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "texture": controls["texture"],
        "percussion": controls["percussion"],
        "notes": [
            "Museformer output is used as pitch material; simple early-stage voice allocation maps it to three visible tracks.",
            "Natural-language style_prompt is accepted for compatibility but does not tune pitch, harmony, density, or orchestration.",
        ],
    }


def transform_lead_notes(user_melody, controls: Optional[Dict[str, Any]] = None):
    if not user_melody:
        return []

    lead_notes = []

    for note in sorted(user_melody, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        duration = max(1, min(TOTAL_STEPS - step, int(round(note.get("duration", 1)))))
        user_pitch = read_pitch_index(note)
        lead_notes.append(
            {
                "id": f"lead_{step}_{user_pitch}_{random.randint(1000, 9999)}",
                "step": step,
                "pitch": user_pitch,
                "duration": duration,
                "voice": "user",
            }
        )

    return lead_notes


def build_arrangement_phases(
    lead_notes,
    generated_notes,
    controls: Optional[Dict[str, Any]] = None,
):
    if not lead_notes:
        return []

    active_controls = controls or DEFAULT_CONTROLS
    phases = []
    generated_by_voice: Dict[str, List[Dict[str, Any]]] = {}
    for note in generated_notes:
        generated_by_voice.setdefault(note["voice"], []).append(note)

    phase_notes = list(lead_notes)
    phases.append(
        {
            "index": 1,
            "label": "主旋律敦煌化",
            "bars": 4,
            "voices": ["user"],
            "notes": phase_notes,
        }
    )

    reveal_voices = list(DUNHUANG_TRACK_VOICES if active_controls.get("texture") == "dunhuang_quartet" else GENERATED_VOICES)
    if active_controls.get("percussion"):
        reveal_voices.append(PERCUSSION_VOICE)

    visible_voices = ["user"]
    for index, voice in enumerate(reveal_voices, start=2):
        visible_voices.append(voice)
        phase_notes = list(lead_notes)
        for visible_voice in reveal_voices[: index - 1]:
            phase_notes.extend(generated_by_voice.get(visible_voice, []))
        phases.append(
            {
                "index": index,
                "label": ARRANGEMENT_PHASE_LABELS.get(voice, f"加入{voice}"),
                "bars": 4,
                "voices": list(visible_voices),
                "notes": phase_notes,
            }
        )

    return phases


def build_prompt_token_strs(melody_json):
    if not melody_json:
        return []

    midi_obj = miditoolkit.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    midi_obj.time_signature_changes.append(miditoolkit.TimeSignature(4, 4, 0))
    midi_obj.tempo_changes.append(miditoolkit.TempoChange(120, 0))

    inst = miditoolkit.Instrument(program=0, is_drum=False, name="user")
    for note in sorted(melody_json, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        duration_steps = max(1, min(TOTAL_STEPS - step, int(round(note.get("duration", 1)))))
        pitch_index = read_pitch_index(note)
        midi_pitch = pitch_index_to_midi(pitch_index)
        start = step * TICKS_PER_STEP
        inst.notes.append(
            miditoolkit.Note(
                velocity=64,
                pitch=midi_pitch,
                start=start,
                end=start + duration_steps * TICKS_PER_STEP,
            )
        )

    if not inst.notes:
        return []

    midi_obj.instruments.append(inst)
    token_lists = midi_encoder.encode_file(
        "prompt.mid",
        midi_obj=midi_obj,
        ignore_ts=True,
    )
    return midi_encoder.convert_token_lists_to_token_str_lists(token_lists)[0]


def parse_generated_pitch_candidates(token_strs, prompt_token_count: int):
    generated_token_strs = token_strs[prompt_token_count:]
    step_candidates = {}
    current_inst = 0
    current_offset = None
    collected_any = False

    for token_str in generated_token_strs:
        token_type, sep, raw_value = token_str.partition("-")
        if not sep:
            continue
        try:
            value = int(raw_value)
        except ValueError:
            continue

        if token_type == "b":
            if collected_any:
                break
            current_inst = 0
            current_offset = None
            continue

        if token_type == "o":
            current_offset = value
            continue

        if token_type == "i":
            current_inst = value
            continue

        if token_type != "p" or current_offset is None:
            continue

        step = max(0, min(TOTAL_STEPS - 1, int(round(current_offset / POS_PER_STEP))))
        step_candidates.setdefault(step, []).append((value, current_inst))
        collected_any = True

    return step_candidates


def get_step_candidate_pitches(
    step: int,
    step_candidates: Dict[int, List[Tuple[int, int]]],
):
    for radius in range(0, 3):
        for candidate_step in (step - radius, step + radius):
            if candidate_step not in step_candidates:
                continue
            candidate_pitches = []
            seen = set()
            for midi_pitch, _inst_id in step_candidates[candidate_step]:
                pitch_index = midi_to_pitch_index(midi_pitch)
                if pitch_index in seen:
                    continue
                seen.add(pitch_index)
                candidate_pitches.append(pitch_index)
            if candidate_pitches:
                return candidate_pitches
    return []


def choose_voice_pitch(
    voice: str,
    user_pitch: int,
    candidate_pitches: List[int],
    used_pitches: Set[int],
    previous_voice_pitch: Optional[int],
    lower_bound_midi: Optional[int],
) -> Optional[int]:
    user_midi = pitch_index_to_midi(user_pitch)
    target_midi = user_midi + VOICE_TARGET_INTERVALS[voice]
    range_min, range_max = VOICE_PITCH_RANGES[voice]

    def score_pitch(pitch_index: int) -> float:
        candidate_midi = pitch_index_to_midi(pitch_index)
        score = abs(candidate_midi - target_midi)

        if previous_voice_pitch is not None:
            previous_midi = pitch_index_to_midi(previous_voice_pitch)
            score += abs(candidate_midi - previous_midi) * 0.45

        if lower_bound_midi is not None and candidate_midi <= lower_bound_midi:
            score += (lower_bound_midi - candidate_midi + 1) * 4

        if pitch_index < range_min:
            score += (range_min - pitch_index) * 6
        elif pitch_index > range_max:
            score += (pitch_index - range_max) * 6

        return score

    available_candidates = [
        pitch for pitch in candidate_pitches
        if pitch not in used_pitches and pitch != user_pitch
    ]
    in_range_candidates = [
        pitch for pitch in available_candidates
        if range_min <= pitch <= range_max
    ]
    if in_range_candidates:
        return min(in_range_candidates, key=score_pitch)

    fallback_pitches = [
        pitch for pitch in ALLOWED_PITCHES
        if pitch not in used_pitches and pitch != user_pitch
    ]
    in_range_fallback_pitches = [
        pitch for pitch in fallback_pitches
        if range_min <= pitch <= range_max
    ]
    if in_range_fallback_pitches:
        return min(in_range_fallback_pitches, key=score_pitch)

    if available_candidates:
        return min(available_candidates, key=score_pitch)

    if not fallback_pitches:
        return None

    return min(fallback_pitches, key=score_pitch)


def arrange_harmony_notes(user_melody, step_candidates):
    if not user_melody:
        return []

    generated_notes = []
    previous_voice_pitches: Dict[str, Optional[int]] = {
        "xiao": None,
        "pipa": None,
        "guqin": None,
    }

    for note in sorted(user_melody, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        user_pitch = read_pitch_index(note)
        candidate_pitches = get_step_candidate_pitches(step, step_candidates)
        used_pitches = {user_pitch}
        selected_voice_pitches: Dict[str, int] = {}

        guqin_pitch = choose_voice_pitch(
            "guqin",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["guqin"],
            lower_bound_midi=None,
        )
        if guqin_pitch is not None:
            selected_voice_pitches["guqin"] = guqin_pitch
            used_pitches.add(guqin_pitch)

        guqin_midi = pitch_index_to_midi(guqin_pitch) if guqin_pitch is not None else None
        pipa_pitch = choose_voice_pitch(
            "pipa",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["pipa"],
            lower_bound_midi=guqin_midi,
        )
        if pipa_pitch is not None:
            selected_voice_pitches["pipa"] = pipa_pitch
            used_pitches.add(pipa_pitch)

        pipa_midi = pitch_index_to_midi(pipa_pitch) if pipa_pitch is not None else guqin_midi
        xiao_pitch = choose_voice_pitch(
            "xiao",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["xiao"],
            lower_bound_midi=pipa_midi,
        )
        if xiao_pitch is not None:
            selected_voice_pitches["xiao"] = xiao_pitch
            used_pitches.add(xiao_pitch)

        for voice in DUNHUANG_TRACK_VOICES:
            chosen_pitch = selected_voice_pitches.get(voice)
            if chosen_pitch is None:
                continue
            previous_voice_pitches[voice] = chosen_pitch
            generated_notes.append(
                {
                    "id": f"ai_{voice}_{step}_{chosen_pitch}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": chosen_pitch,
                    "duration": max(1, min(TOTAL_STEPS - step, int(round(note.get("duration", 1))))),
                    "voice": voice,
                }
            )

    return generated_notes


model_loaded = False
error_msg = ""

try:
    from fairseq import checkpoint_utils, options, tasks
    import midiprocessor as mp

    print("正在将 Museformer 模型加载到 GPU 显存...")
    parser = options.get_generation_parser()
    args = options.parse_args_and_arch(
        parser,
        [
            str(MUSEFORMER_ROOT / "data-bin" / "lmd6remi"),
            "--path",
            str(MUSEFORMER_ROOT / "checkpoints" / "mf-lmd6remi-1" / "checkpoint_best.pt"),
            "--task",
            "museformer_language_modeling",
            "--user-dir",
            str(MUSEFORMER_ROOT / "museformer"),
            "--batch-size",
            "1",
            "--beam",
            "1",
            "--sampling",
            "--temperature",
            "1.0",
        ],
    )
    models, _model_args, task = checkpoint_utils.load_model_ensemble_and_task(
        [args.path],
        arg_overrides=eval(args.model_overrides),
        task=tasks.setup_task(args),
    )
    model = models[0]
    model.eval()
    model.cuda()
    generator = task.build_generator(models, args)
    dictionary = task.target_dictionary
    midi_encoder = mp.MidiEncoder("REMIGEN")
    model_loaded = True
    print("Museformer 模型已成功加载到 GPU！准备就绪。")
except Exception as exc:
    error_msg = str(exc)
    print(f"模型加载异常: {exc}")


@app.post("/generate")
async def generate_music(request: MelodyRequest):
    if not model_loaded:
        raise HTTPException(status_code=500, detail=f"模型未成功加载到 GPU，错误信息: {error_msg}")

    try:
        controls = normalize_controls(request.style_prompt, request.controls)
        transformed_lead_notes = transform_lead_notes(request.melody, controls)
        prompt_token_strs = build_prompt_token_strs(transformed_lead_notes)
        if not prompt_token_strs:
            return {
                "status": "success",
                "lead_notes": [],
                "generated_notes": [],
                "phases": [],
                "controls": controls_metadata(controls),
            }

        prompt_text = " ".join(prompt_token_strs)
        input_ids = dictionary.encode_line(
            prompt_text,
            add_if_not_exist=False,
            append_eos=False,
        ).long().cuda()

        unk_count = int((input_ids == dictionary.unk()).sum().item())
        if unk_count:
            raise RuntimeError(f"输入旋律编码后包含 {unk_count} 个未知 token")

        sample = {
            "net_input": {
                "src_tokens": input_ids.unsqueeze(0),
                "src_lengths": torch.LongTensor([input_ids.numel()]).cuda(),
            }
        }

        print(">>> 开始 GPU 真实推理 <<<")
        with torch.no_grad():
            results = task.inference_step(
                generator,
                models,
                sample,
                prefix_tokens=input_ids.unsqueeze(0),
            )

        generated_ids = results[0][0]["tokens"]
        generated_token_strs = dictionary.string(generated_ids).split()
        generated_notes = decode_generated_notes(generated_token_strs, len(prompt_token_strs))
        phases = build_arrangement_phases(transformed_lead_notes, generated_notes, controls)
        print(f"GPU 推理成功，返回 {len(generated_notes)} 个音符。")
        return {
            "status": "success",
            "lead_notes": transformed_lead_notes,
            "generated_notes": generated_notes,
            "phases": phases,
            "controls": controls_metadata(controls),
        }
    except Exception as exc:
        print(f"GPU 推理过程中出错: {exc}")
        raise HTTPException(status_code=500, detail=f"GPU 推理失败: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

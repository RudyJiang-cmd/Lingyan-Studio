import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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


TOTAL_STEPS = 16
TICKS_PER_BEAT = 480
TICKS_PER_STEP = TICKS_PER_BEAT // 4
POS_PER_STEP = 3
GENERATED_VOICES = ("alto", "tenor", "bass")
ALLOWED_PITCHES = (0, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14)
VOICE_TARGET_INTERVALS = {
    "alto": -3,
    "tenor": -8,
    "bass": -14,
}
VOICE_PITCH_RANGES = {
    "alto": (6, 12),
    "tenor": (9, 13),
    "bass": (11, 14),
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
    for pitch_index in ALLOWED_PITCHES:
        candidate_midi = PITCH_TO_MIDI[pitch_index]
        diff = abs(midi_pitch - candidate_midi)
        if diff < best_diff:
            best_diff = diff
            best_pitch_index = pitch_index
    return best_pitch_index


def pitch_index_to_midi(pitch_index: int) -> int:
    return PITCH_TO_MIDI[pitch_index]


def build_prompt_token_strs(melody_json):
    if not melody_json:
        return []

    midi_obj = miditoolkit.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    midi_obj.time_signature_changes.append(miditoolkit.TimeSignature(4, 4, 0))
    midi_obj.tempo_changes.append(miditoolkit.TempoChange(120, 0))

    inst = miditoolkit.Instrument(program=0, is_drum=False, name="user")
    for note in sorted(melody_json, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        pitch_index = int(round(note.get("pitch", 14)))
        midi_pitch = PITCH_TO_MIDI.get(pitch_index, 60)
        start = step * TICKS_PER_STEP
        inst.notes.append(
            miditoolkit.Note(
                velocity=64,
                pitch=midi_pitch,
                start=start,
                end=start + TICKS_PER_STEP,
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
        "alto": None,
        "tenor": None,
        "bass": None,
    }
    for note in sorted(user_melody, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        user_pitch = int(round(note.get("pitch", 14)))
        candidate_pitches = get_step_candidate_pitches(step, step_candidates)
        used_pitches = {user_pitch}
        user_midi = pitch_index_to_midi(user_pitch)
        selected_voice_pitches: Dict[str, int] = {}

        bass_pitch = choose_voice_pitch(
            "bass",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["bass"],
            lower_bound_midi=None,
        )
        if bass_pitch is not None:
            selected_voice_pitches["bass"] = bass_pitch
            used_pitches.add(bass_pitch)

        bass_midi = pitch_index_to_midi(bass_pitch) if bass_pitch is not None else None
        tenor_pitch = choose_voice_pitch(
            "tenor",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["tenor"],
            lower_bound_midi=bass_midi,
        )
        if tenor_pitch is not None:
            selected_voice_pitches["tenor"] = tenor_pitch
            used_pitches.add(tenor_pitch)

        tenor_midi = pitch_index_to_midi(tenor_pitch) if tenor_pitch is not None else bass_midi
        alto_pitch = choose_voice_pitch(
            "alto",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["alto"],
            lower_bound_midi=tenor_midi,
        )
        if alto_pitch is not None:
            selected_voice_pitches["alto"] = alto_pitch
            used_pitches.add(alto_pitch)

        for voice in GENERATED_VOICES:
            chosen_pitch = selected_voice_pitches.get(voice)
            if chosen_pitch is None:
                continue
            previous_voice_pitches[voice] = chosen_pitch
            generated_notes.append(
                {
                    "id": f"ai_{voice}_{step}_{chosen_pitch}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": chosen_pitch,
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
        prompt_token_strs = build_prompt_token_strs(request.melody)
        if not prompt_token_strs:
            return {"status": "success", "generated_notes": []}

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
        step_candidates = parse_generated_pitch_candidates(generated_token_strs, len(prompt_token_strs))
        generated_notes = arrange_harmony_notes(request.melody, step_candidates)
        print(f"GPU 推理成功，返回 {len(generated_notes)} 个音符。")
        return {"status": "success", "generated_notes": generated_notes}
    except Exception as exc:
        print(f"GPU 推理过程中出错: {exc}")
        raise HTTPException(status_code=500, detail=f"GPU 推理失败: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

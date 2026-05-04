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
TICKS_PER_STEP = TICKS_PER_BEAT
POS_PER_STEP = 12
GENERATED_VOICES = ("alto", "tenor", "bass")
DUNHUANG_TRACK_VOICES = ("xiao", "pipa", "guqin")
PERCUSSION_VOICE = "percussion"
ALLOWED_PITCHES = (0, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14)
ANCHOR_PITCHES = (14, 10, 7, 4)
CADENCE_PITCHES = (14, 10, 7)
VOICE_TARGET_INTERVALS = {
    "alto": -3,
    "tenor": -8,
    "bass": -14,
    "xiao": -2,
    "pipa": -7,
    "guqin": -14,
}
VOICE_PITCH_RANGES = {
    "alto": (6, 12),
    "tenor": (9, 13),
    "bass": (11, 14),
    "xiao": (5, 12),
    "pipa": (8, 13),
    "guqin": (11, 14),
}
VOICE_SMOOTHING_WEIGHTS = {
    "alto": 0.45,
    "tenor": 0.45,
    "bass": 0.45,
    "xiao": 0.65,
    "pipa": 0.3,
    "guqin": 0.5,
}
RHYTHM_PATTERNS = {
    "sparse": {
        "xiao": (0, 4, 8, 12),
        "pipa": (0, 2, 4, 6, 8, 10, 12, 14),
        "guqin": (0, 4, 8, 12),
        "percussion": (0, 4, 8, 12),
    },
    "steady": {
        "xiao": tuple(range(0, TOTAL_STEPS, 2)),
        "pipa": tuple(range(TOTAL_STEPS)),
        "guqin": (0, 2, 4, 6, 8, 10, 12, 14),
        "percussion": (0, 2, 4, 6, 8, 10, 12, 14),
    },
    "dance": {
        "xiao": tuple(range(0, TOTAL_STEPS, 2)),
        "pipa": tuple(range(TOTAL_STEPS)),
        "guqin": (0, 3, 4, 7, 8, 11, 12, 15),
        "percussion": tuple(range(TOTAL_STEPS)),
    },
}
DEFAULT_CONTROLS = {
    "style": "dunhuang",
    "texture": "satb",
    "rhythm_profile": "steady",
    "dunhuang_level": 0.75,
    "density": 0.65,
    "bass_motion": 0.45,
    "cadence_strength": 0.65,
    "percussion": False,
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


def read_pitch_index(note) -> int:
    raw_pitch = int(round(note.get("pitch", note.get("midi", 14))))
    if raw_pitch in PITCH_TO_MIDI:
        return raw_pitch
    return midi_to_pitch_index(raw_pitch)


def clamp01(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_controls(style_prompt: Optional[str], controls: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = dict(DEFAULT_CONTROLS)
    if controls:
        normalized.update({key: value for key, value in controls.items() if value is not None})

    prompt = (style_prompt or "").lower()
    if style_prompt:
        normalized["style_prompt"] = style_prompt

    dunhuang_words = ("敦煌", "dunhuang", "雅乐", "西域", "壁画", "飞天", "石窟")
    dance_words = ("节奏", "鼓", "鼓点", "舞", "律动", "动感", "强拍", "颗粒", "dance", "drum", "rhythm")
    sparse_words = ("空灵", "慢", "散板", "稀疏", "留白", "悠远", "sparse", "slow")
    quartet_words = ("箫", "琵琶", "古琴", "四重奏", "配器", "音轨", "track", "instrument")
    bass_words = ("低音", "低声部", "bass", "古琴")

    if any(word in prompt for word in dunhuang_words):
        normalized["style"] = "dunhuang"
        normalized["dunhuang_level"] = max(clamp01(normalized.get("dunhuang_level"), 0.75), 0.85)
        normalized["cadence_strength"] = max(clamp01(normalized.get("cadence_strength"), 0.65), 0.75)
    if any(word in prompt for word in dance_words):
        normalized["rhythm_profile"] = "dance"
        normalized["density"] = max(clamp01(normalized.get("density"), 0.65), 0.75)
    if any(word in prompt for word in sparse_words):
        normalized["rhythm_profile"] = "sparse"
        normalized["density"] = min(clamp01(normalized.get("density"), 0.65), 0.45)
    if any(word in prompt for word in quartet_words):
        normalized["texture"] = "dunhuang_quartet"
    if any(word in prompt for word in bass_words):
        normalized["bass_motion"] = max(clamp01(normalized.get("bass_motion"), 0.45), 0.7)
    if "鼓" in prompt or "drum" in prompt or "percussion" in prompt:
        normalized["percussion"] = True
        normalized["texture"] = "dunhuang_quartet"

    normalized["dunhuang_level"] = clamp01(normalized.get("dunhuang_level"), 0.75)
    normalized["density"] = clamp01(normalized.get("density"), 0.65)
    normalized["bass_motion"] = clamp01(normalized.get("bass_motion"), 0.45)
    normalized["cadence_strength"] = clamp01(normalized.get("cadence_strength"), 0.65)
    if normalized.get("rhythm_profile") not in RHYTHM_PATTERNS:
        normalized["rhythm_profile"] = "steady"
    if normalized.get("texture") not in ("satb", "dunhuang_quartet"):
        normalized["texture"] = "satb"
    normalized["percussion"] = bool(normalized.get("percussion"))
    return normalized


def should_emit_step(voice: str, step: int, controls: Dict[str, Any]) -> bool:
    pattern = RHYTHM_PATTERNS[controls["rhythm_profile"]].get(voice)
    if pattern is None:
        return True
    if step in pattern:
        return True
    if voice == "pipa" and controls["density"] >= 0.7:
        return True
    if voice == "xiao" and controls["density"] >= 0.85 and step % 2 == 1:
        return True
    return False


def is_strong_step(step: int) -> bool:
    return step % 4 in (0, 2)


def nearest_pitch_from_set(user_pitch: int, pitch_set: Tuple[int, ...], used_pitches: Set[int]) -> Optional[int]:
    available = [pitch for pitch in pitch_set if pitch not in used_pitches and pitch != user_pitch]
    if not available:
        return None
    user_midi = pitch_index_to_midi(user_pitch)
    return min(available, key=lambda pitch: abs(pitch_index_to_midi(pitch) - user_midi))


def controls_metadata(controls: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "style": controls["style"],
        "texture": controls["texture"],
        "rhythm_profile": controls["rhythm_profile"],
        "dunhuang_level": controls["dunhuang_level"],
        "density": controls["density"],
        "bass_motion": controls["bass_motion"],
        "cadence_strength": controls["cadence_strength"],
        "percussion": controls["percussion"],
        "notes": [
            "Natural-language style_prompt is converted into structured controls before post-processing.",
            "Museformer still receives a musical REMIGEN prefix; text is not passed directly to the model.",
        ],
    }


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
    controls: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    active_controls = controls or DEFAULT_CONTROLS
    user_midi = pitch_index_to_midi(user_pitch)
    target_midi = user_midi + VOICE_TARGET_INTERVALS[voice]
    range_min, range_max = VOICE_PITCH_RANGES[voice]
    dunhuang_level = clamp01(active_controls.get("dunhuang_level"), DEFAULT_CONTROLS["dunhuang_level"])
    cadence_strength = clamp01(active_controls.get("cadence_strength"), DEFAULT_CONTROLS["cadence_strength"])
    bass_motion = clamp01(active_controls.get("bass_motion"), DEFAULT_CONTROLS["bass_motion"])

    def score_pitch(pitch_index: int) -> float:
        candidate_midi = pitch_index_to_midi(pitch_index)
        score = abs(candidate_midi - target_midi)

        if previous_voice_pitch is not None:
            previous_midi = pitch_index_to_midi(previous_voice_pitch)
            motion = abs(candidate_midi - previous_midi)
            score += motion * VOICE_SMOOTHING_WEIGHTS.get(voice, 0.45)
            if voice in ("bass", "guqin") and motion == 0:
                score += bass_motion * 7

        if lower_bound_midi is not None and candidate_midi <= lower_bound_midi:
            score += (lower_bound_midi - candidate_midi + 1) * 4

        if pitch_index < range_min:
            score += (range_min - pitch_index) * 6
        elif pitch_index > range_max:
            score += (pitch_index - range_max) * 6

        if active_controls.get("style") == "dunhuang":
            if pitch_index in ANCHOR_PITCHES:
                score -= 2.5 * dunhuang_level
            if pitch_index in CADENCE_PITCHES:
                score -= 1.5 * cadence_strength
            if pitch_index in (4, 11):
                score -= 2.0 * dunhuang_level

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


def arrange_harmony_notes(user_melody, step_candidates, controls: Optional[Dict[str, Any]] = None):
    if not user_melody:
        return []

    active_controls = controls or DEFAULT_CONTROLS
    output_voices = DUNHUANG_TRACK_VOICES if active_controls.get("texture") == "dunhuang_quartet" else GENERATED_VOICES
    generated_notes = []
    previous_voice_pitches: Dict[str, Optional[int]] = {
        voice: None for voice in set(GENERATED_VOICES + DUNHUANG_TRACK_VOICES)
    }
    for note in sorted(user_melody, key=lambda item: item.get("step", 0)):
        step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        user_pitch = read_pitch_index(note)
        candidate_pitches = get_step_candidate_pitches(step, step_candidates)
        used_pitches = {user_pitch}
        selected_voice_pitches: Dict[str, int] = {}

        bass_voice = "guqin" if active_controls.get("texture") == "dunhuang_quartet" else "bass"
        mid_voice = "pipa" if active_controls.get("texture") == "dunhuang_quartet" else "tenor"
        high_voice = "xiao" if active_controls.get("texture") == "dunhuang_quartet" else "alto"

        bass_pitch = choose_voice_pitch(
            bass_voice,
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches[bass_voice],
            lower_bound_midi=None,
            controls=active_controls,
        )
        if bass_pitch is not None:
            if active_controls.get("style") == "dunhuang" and is_strong_step(step):
                anchor_pitch = nearest_pitch_from_set(user_pitch, CADENCE_PITCHES, used_pitches)
                if anchor_pitch is not None and random.random() < active_controls["cadence_strength"] * 0.35:
                    bass_pitch = anchor_pitch
            selected_voice_pitches[bass_voice] = bass_pitch
            used_pitches.add(bass_pitch)

        bass_midi = pitch_index_to_midi(bass_pitch) if bass_pitch is not None else None
        mid_pitch = choose_voice_pitch(
            mid_voice,
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches[mid_voice],
            lower_bound_midi=bass_midi,
            controls=active_controls,
        )
        if mid_pitch is not None:
            selected_voice_pitches[mid_voice] = mid_pitch
            used_pitches.add(mid_pitch)

        mid_midi = pitch_index_to_midi(mid_pitch) if mid_pitch is not None else bass_midi
        high_pitch = choose_voice_pitch(
            high_voice,
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches[high_voice],
            lower_bound_midi=mid_midi,
            controls=active_controls,
        )
        if high_pitch is not None:
            selected_voice_pitches[high_voice] = high_pitch
            used_pitches.add(high_pitch)

        for voice in output_voices:
            if not should_emit_step(voice, step, active_controls):
                continue
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

        if active_controls.get("percussion") and should_emit_step(PERCUSSION_VOICE, step, active_controls):
            generated_notes.append(
                {
                    "id": f"ai_percussion_{step}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": 10 if is_strong_step(step) else 12,
                    "duration": 1,
                    "voice": PERCUSSION_VOICE,
                    "instrument": "percussion",
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
        prompt_token_strs = build_prompt_token_strs(request.melody)
        if not prompt_token_strs:
            return {"status": "success", "generated_notes": [], "controls": controls_metadata(controls)}

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
        generated_notes = arrange_harmony_notes(request.melody, step_candidates, controls)
        print(f"GPU 推理成功，返回 {len(generated_notes)} 个音符。")
        return {
            "status": "success",
            "generated_notes": generated_notes,
            "controls": controls_metadata(controls),
        }
    except Exception as exc:
        print(f"GPU 推理过程中出错: {exc}")
        raise HTTPException(status_code=500, detail=f"GPU 推理失败: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

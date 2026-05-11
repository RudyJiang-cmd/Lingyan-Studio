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
    "xiao": 2,
    "pipa": -5,
    "guqin": -12,
}
VOICE_PITCH_RANGES = {
    "xiao": (5, 10),
    "pipa": (7, 13),
    "guqin": (10, 14),
}
VOICE_MOTION_WEIGHTS = {
    "xiao": 0.45,
    "pipa": 0.3,
    "guqin": 0.8,
}
VOICE_REPEAT_PENALTIES = {
    "xiao": 2.0,
    "pipa": 5.0,
    "guqin": 2.5,
}
VOICE_STABLE_PITCHES = {
    "xiao": (5, 7, 9),
    "pipa": (7, 9, 12),
    "guqin": (10, 14),
}
AVOID_INTERVAL_CLASSES = {1, 2, 6, 10, 11}
DENSE_INTERVAL_CLASSES = {0, 5}
GUQIN_RHYTHM_GROUPS = ((0, 3), (3, 3), (6, 2), (8, 3), (11, 3), (14, 2))
GUQIN_RHYTHM_STEPS = {
    step
    for start, duration in GUQIN_RHYTHM_GROUPS
    for step in range(start, min(TOTAL_STEPS, start + duration))
}
XIAO_RHYTHM_STEPS = {0, 4, 8, 11, 14}
CADENCE_STEPS = {11, 15}
TAPERED_STEPS = {3, 7, 11, 15}
DRONE_STEPS = {0, 4, 8, 12}
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
    "guqin": "加入都塔尔低音",
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
            "Museformer output is used as pitch material; post-processing emphasizes modal texture, open fifths, and sustained bass.",
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
    same_step_pitches: Optional[Set[int]] = None,
) -> Optional[int]:
    user_midi = pitch_index_to_midi(user_pitch)
    target_midi = user_midi + VOICE_TARGET_INTERVALS[voice]
    range_min, range_max = VOICE_PITCH_RANGES[voice]
    stable_pitches = VOICE_STABLE_PITCHES[voice]
    comparison_pitches = set(same_step_pitches or set())

    def interval_class_against_same_step(pitch_index: int) -> List[int]:
        return [
            interval_class_between(pitch_index, other_pitch)
            for other_pitch in comparison_pitches
            if other_pitch != pitch_index
        ]

    def has_avoidable_interval(pitch_index: int) -> bool:
        return has_avoidable_interval_against(pitch_index, comparison_pitches)

    def score_pitch(pitch_index: int) -> float:
        candidate_midi = pitch_index_to_midi(pitch_index)
        score = abs(candidate_midi - target_midi) * (0.75 if voice == "guqin" else 1.0)

        for interval in interval_class_against_same_step(pitch_index):
            if interval in AVOID_INTERVAL_CLASSES:
                score += 80
            elif interval in DENSE_INTERVAL_CLASSES:
                score += 5
            elif interval in (3, 4, 7):
                score -= 1.2

        if previous_voice_pitch is not None:
            previous_midi = pitch_index_to_midi(previous_voice_pitch)
            motion = abs(candidate_midi - previous_midi)
            score += motion * VOICE_MOTION_WEIGHTS[voice]
            if pitch_index == previous_voice_pitch:
                score += VOICE_REPEAT_PENALTIES[voice]

        if lower_bound_midi is not None and candidate_midi <= lower_bound_midi:
            score += (lower_bound_midi - candidate_midi + 1) * 4

        if pitch_index in stable_pitches:
            score -= 1.2 if voice == "guqin" else 0.6
        else:
            score += 0.35

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
    consonant_in_range_candidates = [
        pitch for pitch in in_range_candidates
        if not has_avoidable_interval(pitch)
    ]
    if consonant_in_range_candidates:
        return min(consonant_in_range_candidates, key=score_pitch)

    fallback_pitches = [
        pitch for pitch in ALLOWED_PITCHES
        if pitch not in used_pitches and pitch != user_pitch
    ]
    in_range_fallback_pitches = [
        pitch for pitch in fallback_pitches
        if range_min <= pitch <= range_max
    ]
    consonant_in_range_fallback_pitches = [
        pitch for pitch in in_range_fallback_pitches
        if not has_avoidable_interval(pitch)
    ]
    if consonant_in_range_fallback_pitches:
        return min(consonant_in_range_fallback_pitches, key=score_pitch)

    consonant_available_candidates = [
        pitch for pitch in available_candidates
        if not has_avoidable_interval(pitch)
    ]
    if consonant_available_candidates:
        return min(consonant_available_candidates, key=score_pitch)

    consonant_fallback_pitches = [
        pitch for pitch in fallback_pitches
        if not has_avoidable_interval(pitch)
    ]
    if consonant_fallback_pitches:
        return min(consonant_fallback_pitches, key=score_pitch)

    if in_range_candidates:
        return min(in_range_candidates, key=score_pitch)

    if in_range_fallback_pitches:
        return min(in_range_fallback_pitches, key=score_pitch)

    if available_candidates:
        return min(available_candidates, key=score_pitch)

    if not fallback_pitches:
        return None

    return min(fallback_pitches, key=score_pitch)


def nearest_stable_pitch(voice: str, target_pitch: int) -> int:
    stable_pitches = VOICE_STABLE_PITCHES[voice]
    range_min, range_max = VOICE_PITCH_RANGES[voice]
    in_range_stable_pitches = [
        pitch for pitch in stable_pitches
        if range_min <= pitch <= range_max
    ]
    if not in_range_stable_pitches:
        in_range_stable_pitches = list(range(range_min, range_max + 1))
    return min(
        in_range_stable_pitches,
        key=lambda pitch: abs(pitch_index_to_midi(pitch) - pitch_index_to_midi(target_pitch)),
    )


def interval_class_between(left_pitch: int, right_pitch: int) -> int:
    interval = abs(pitch_index_to_midi(left_pitch) - pitch_index_to_midi(right_pitch)) % 12
    return min(interval, 12 - interval)


def has_avoidable_interval_against(pitch: int, comparison_pitches: Set[int]) -> bool:
    return any(
        interval_class_between(pitch, other_pitch) in AVOID_INTERVAL_CLASSES
        for other_pitch in comparison_pitches
        if other_pitch != pitch
    )


def nearest_consonant_stable_pitch(voice: str, target_pitch: int, same_step_pitches: Set[int]) -> int:
    stable_pitches = VOICE_STABLE_PITCHES[voice]
    range_min, range_max = VOICE_PITCH_RANGES[voice]
    in_range_stable_pitches = [
        pitch for pitch in stable_pitches
        if range_min <= pitch <= range_max
    ] or list(range(range_min, range_max + 1))

    consonant_stable_pitches = [
        pitch for pitch in in_range_stable_pitches
        if not has_avoidable_interval_against(pitch, same_step_pitches)
    ]
    if consonant_stable_pitches:
        return min(
            consonant_stable_pitches,
            key=lambda pitch: abs(pitch_index_to_midi(pitch) - pitch_index_to_midi(target_pitch)),
        )
    return nearest_stable_pitch(voice, target_pitch)


def nearest_consonant_voice_pitch(voice: str, target_pitch: int, comparison_pitches: Set[int]) -> int:
    range_min, range_max = VOICE_PITCH_RANGES[voice]
    stable_pitches = set(VOICE_STABLE_PITCHES[voice])
    in_range_pitches = list(range(range_min, range_max + 1))
    consonant_pitches = [
        pitch for pitch in in_range_pitches
        if not has_avoidable_interval_against(pitch, comparison_pitches)
    ]
    if not consonant_pitches:
        return target_pitch
    return min(
        consonant_pitches,
        key=lambda pitch: (
            0 if pitch in stable_pitches else 1,
            abs(pitch_index_to_midi(pitch) - pitch_index_to_midi(target_pitch)),
        ),
    )


def shape_voice_duration(voice: str, note: Dict[str, Any], next_step: Optional[int]) -> int:
    step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
    source_duration = max(1, min(TOTAL_STEPS - step, int(round(note.get("duration", 1)))))
    space_to_next = TOTAL_STEPS - step if next_step is None else max(1, next_step - step)

    if voice == "xiao":
        return max(2, min(source_duration, space_to_next, 4))
    if voice == "pipa":
        return 1
    if voice == "guqin":
        if step in DRONE_STEPS:
            return max(2, min(space_to_next, 4))
        return max(2, min(source_duration, space_to_next, 4))
    return source_duration


def guqin_group_duration(step: int) -> Optional[int]:
    for group_start, group_duration in GUQIN_RHYTHM_GROUPS:
        if step == group_start:
            return group_duration
    return None


def guqin_group_for_step(step: int) -> Optional[Tuple[int, int]]:
    for group_start, group_duration in GUQIN_RHYTHM_GROUPS:
        if group_start <= step < min(TOTAL_STEPS, group_start + group_duration):
            return group_start, group_duration
    return None


def melody_note_at_or_before_step(sorted_melody: List[Dict[str, Any]], step: int) -> Optional[Dict[str, Any]]:
    previous_note = None
    for note in sorted_melody:
        note_step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        if note_step > step:
            break
        previous_note = note
    return previous_note


def clamp_duration_to_consonant_steps(
    pitch: int,
    step: int,
    duration: int,
    melody_by_step: Dict[int, Set[int]],
) -> int:
    safe_duration = max(1, min(TOTAL_STEPS - step, duration))
    for active_step in range(step + 1, min(TOTAL_STEPS, step + safe_duration)):
        if has_avoidable_interval_against(pitch, melody_by_step.get(active_step, set())):
            return max(1, active_step - step)
    return safe_duration


def pitches_sounding_during_steps(
    notes: List[Dict[str, Any]],
    start_step: int,
    duration: int,
) -> Set[int]:
    sounding_pitches = set()
    for active_step in range(start_step, min(TOTAL_STEPS, start_step + duration)):
        sounding_pitches |= pitches_sounding_at_step(notes, active_step)
    return sounding_pitches


def melody_pitches_during_steps(
    melody_by_step: Dict[int, Set[int]],
    start_step: int,
    duration: int,
) -> Set[int]:
    sounding_pitches = set()
    for active_step in range(start_step, min(TOTAL_STEPS, start_step + duration)):
        sounding_pitches |= melody_by_step.get(active_step, set())
    return sounding_pitches


def pitches_sounding_at_step(notes: List[Dict[str, Any]], step: int) -> Set[int]:
    sounding_pitches = set()
    for note in notes:
        note_step = max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0)))))
        duration = max(1, int(round(note.get("duration", 1))))
        if note_step <= step < min(TOTAL_STEPS, note_step + duration):
            sounding_pitches.add(read_pitch_index(note))
    return sounding_pitches


def enforce_guqin_rhythm(generated_notes: List[Dict[str, Any]], melody_by_step: Dict[int, Set[int]]) -> List[Dict[str, Any]]:
    non_guqin_notes = [note for note in generated_notes if note.get("voice") != "guqin"]
    guqin_notes = [note for note in generated_notes if note.get("voice") == "guqin"]
    group_pitches: Dict[int, int] = {}

    for group_start, group_duration in GUQIN_RHYTHM_GROUPS:
        group_note = next(
            (
                note for note in guqin_notes
                if group_start <= int(round(note.get("step", 0))) < group_start + group_duration
            ),
            None,
        )
        comparison_pitches = (
            melody_pitches_during_steps(melody_by_step, group_start, group_duration)
            | pitches_sounding_during_steps(non_guqin_notes, group_start, group_duration)
        )
        if group_note:
            target_pitch = read_pitch_index(group_note)
        elif group_pitches:
            target_pitch = list(group_pitches.values())[-1]
        else:
            target_pitch = 14
        group_pitches[group_start] = nearest_consonant_voice_pitch("guqin", target_pitch, comparison_pitches)

    fixed_guqin_notes = []
    for group_start, group_duration in GUQIN_RHYTHM_GROUPS:
        pitch = group_pitches[group_start]
        for step in range(group_start, min(TOTAL_STEPS, group_start + group_duration)):
            fixed_guqin_notes.append(
                {
                    "id": f"ai_guqin_{step}_{pitch}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": pitch,
                    "duration": 1,
                    "voice": "guqin",
                }
            )

    return non_guqin_notes + fixed_guqin_notes


def arrange_silk_road_tracks(user_melody, step_candidates):
    if not user_melody:
        return []

    sorted_melody = sorted(user_melody, key=lambda item: item.get("step", 0))
    melody_by_step: Dict[int, Set[int]] = {}
    for melody_note in sorted_melody:
        melody_step = max(0, min(TOTAL_STEPS - 1, int(round(melody_note.get("step", 0)))))
        melody_duration = max(1, int(round(melody_note.get("duration", 1))))
        melody_pitch = read_pitch_index(melody_note)
        for active_step in range(melody_step, min(TOTAL_STEPS, melody_step + melody_duration)):
            melody_by_step.setdefault(active_step, set()).add(melody_pitch)

    generated_notes = []
    previous_voice_pitches: Dict[str, Optional[int]] = {
        "xiao": None,
        "pipa": None,
        "guqin": None,
    }
    guqin_group_pitches: Dict[int, int] = {}

    notes_by_step = {
        max(0, min(TOTAL_STEPS - 1, int(round(note.get("step", 0))))): note
        for note in sorted_melody
    }

    for step in range(TOTAL_STEPS):
        note = notes_by_step.get(step) or melody_note_at_or_before_step(sorted_melody, step) or sorted_melody[0]
        if step not in notes_by_step and step not in GUQIN_RHYTHM_STEPS:
            continue
        next_step = next(
            (
                max(0, min(TOTAL_STEPS - 1, int(round(future_note.get("step", 0)))))
                for future_note in sorted_melody
                if max(0, min(TOTAL_STEPS - 1, int(round(future_note.get("step", 0))))) > step
            ),
            None,
        )
        user_pitch = read_pitch_index(note)
        candidate_pitches = get_step_candidate_pitches(step, step_candidates)
        melody_pitches_at_step = melody_by_step.get(step, set())
        used_pitches = set(melody_pitches_at_step)
        selected_voice_pitches: Dict[str, int] = {}
        selected_voice_durations: Dict[str, int] = {}
        same_step_pitches = set(melody_pitches_at_step) | pitches_sounding_at_step(generated_notes, step)

        guqin_group = guqin_group_for_step(step)
        guqin_group_note = melody_note_at_or_before_step(sorted_melody, step) if guqin_group else None

        for voice, lower_voice in (("guqin", None), ("pipa", "guqin"), ("xiao", "pipa")):
            if voice == "guqin" and step not in GUQIN_RHYTHM_STEPS:
                continue
            if voice == "xiao" and step not in XIAO_RHYTHM_STEPS:
                continue
            if voice == "pipa" and step not in notes_by_step:
                continue
            if voice not in ("guqin", "xiao") and step not in notes_by_step:
                continue
            lower_bound_midi = None
            if lower_voice and lower_voice in selected_voice_pitches:
                lower_bound_midi = pitch_index_to_midi(selected_voice_pitches[lower_voice])
            voice_user_pitch = read_pitch_index(guqin_group_note) if voice == "guqin" and guqin_group_note else user_pitch
            voice_same_step_pitches = same_step_pitches
            if voice == "guqin":
                group_start, group_duration = guqin_group or (step, 1)
                voice_same_step_pitches = (
                    melody_pitches_during_steps(melody_by_step, group_start, group_duration)
                    | pitches_sounding_during_steps(generated_notes, group_start, group_duration)
                )
                if group_start in guqin_group_pitches:
                    chosen_pitch = guqin_group_pitches[group_start]
                    if has_avoidable_interval_against(chosen_pitch, same_step_pitches):
                        chosen_pitch = nearest_consonant_voice_pitch("guqin", chosen_pitch, same_step_pitches)
                    selected_voice_pitches[voice] = chosen_pitch
                    used_pitches.add(chosen_pitch)
                    same_step_pitches.add(chosen_pitch)
                    continue
            elif "guqin" in selected_voice_pitches:
                voice_same_step_pitches = same_step_pitches | {selected_voice_pitches["guqin"]}
            chosen_pitch = choose_voice_pitch(
                voice,
                voice_user_pitch,
                candidate_pitches,
                used_pitches,
                previous_voice_pitches[voice],
                lower_bound_midi=lower_bound_midi,
                same_step_pitches=voice_same_step_pitches,
            )
            if chosen_pitch is None:
                continue
            if voice == "guqin" and step in CADENCE_STEPS:
                chosen_pitch = nearest_consonant_voice_pitch("guqin", chosen_pitch, voice_same_step_pitches)
            if voice == "xiao":
                xiao_next_step = next((r for r in sorted(XIAO_RHYTHM_STEPS) if r > step), None)
                xiao_duration_target = max(2, (xiao_next_step - step) if xiao_next_step is not None else 4)
                if step >= 12:
                    xiao_duration_target = 2
                selected_voice_pitches[voice] = chosen_pitch
                selected_voice_durations[voice] = xiao_duration_target
                used_pitches.add(chosen_pitch)
                same_step_pitches.add(chosen_pitch)
                continue
            selected_voice_pitches[voice] = chosen_pitch
            if voice == "guqin" and guqin_group:
                guqin_group_pitches[guqin_group[0]] = chosen_pitch
            used_pitches.add(chosen_pitch)
            same_step_pitches.add(chosen_pitch)

        if "guqin" in selected_voice_pitches and step in DRONE_STEPS:
            same_step_without_guqin = {
                pitch for pitch in same_step_pitches
                if pitch != selected_voice_pitches["guqin"]
            }
            selected_voice_pitches["guqin"] = nearest_consonant_voice_pitch(
                "guqin",
                selected_voice_pitches["guqin"],
                same_step_without_guqin,
            )
            used_pitches.add(selected_voice_pitches["guqin"])
            same_step_pitches.add(selected_voice_pitches["guqin"])
        if "pipa" in selected_voice_pitches and "xiao" in selected_voice_pitches:
            xiao_pitch = selected_voice_pitches["xiao"]
            pipa_pitch = selected_voice_pitches["pipa"]
            if xiao_pitch - pipa_pitch < 2:
                same_step_without_pipa = {
                    pitch for pitch in same_step_pitches
                    if pitch != pipa_pitch
                }
                adjusted_pipa_pitch = max(7, min(13, pipa_pitch - 1))
                selected_voice_pitches["pipa"] = choose_voice_pitch(
                    "pipa",
                    user_pitch,
                    [adjusted_pipa_pitch, pipa_pitch],
                    {pitch for pitch in used_pitches if pitch != pipa_pitch},
                    previous_voice_pitches["pipa"],
                    lower_bound_midi=(
                        pitch_index_to_midi(selected_voice_pitches["guqin"])
                        if "guqin" in selected_voice_pitches
                        else None
                    ),
                    same_step_pitches=same_step_without_pipa,
                ) or adjusted_pipa_pitch

        if "guqin" in selected_voice_pitches:
            group_duration = guqin_group_duration(step) or 1
            guqin_comparison_pitches = (
                melody_pitches_during_steps(melody_by_step, step, group_duration)
                | pitches_sounding_during_steps(generated_notes, step, group_duration)
                | {
                    pitch
                    for voice, pitch in selected_voice_pitches.items()
                    if voice != "guqin"
                }
            )
            if has_avoidable_interval_against(selected_voice_pitches["guqin"], guqin_comparison_pitches):
                selected_voice_pitches["guqin"] = nearest_consonant_voice_pitch(
                    "guqin",
                    selected_voice_pitches["guqin"],
                    guqin_comparison_pitches,
                )
            if guqin_group:
                guqin_group_pitches[guqin_group[0]] = selected_voice_pitches["guqin"]

        for voice in DUNHUANG_TRACK_VOICES:
            chosen_pitch = selected_voice_pitches.get(voice)
            if chosen_pitch is None:
                continue
            previous_voice_pitches[voice] = chosen_pitch
            base_duration = selected_voice_durations.get(
                voice,
                1 if voice == "guqin" else shape_voice_duration(voice, note, next_step),
            )
            duration = clamp_duration_to_consonant_steps(
                chosen_pitch,
                step,
                base_duration or 1,
                melody_by_step,
            )
            generated_notes.append(
                {
                    "id": f"ai_{voice}_{step}_{chosen_pitch}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": chosen_pitch,
                    "duration": duration,
                    "voice": voice,
                }
            )

            if voice == "pipa":
                response_step = step + 1
                if next_step is not None:
                    response_step = min(response_step, next_step - 1)
                if response_step <= step or response_step >= TOTAL_STEPS:
                    continue
                response_candidates = get_step_candidate_pitches(response_step, step_candidates) or candidate_pitches
                response_same_step_pitches = (
                    {user_pitch, chosen_pitch}
                    | melody_by_step.get(response_step, set())
                    | pitches_sounding_at_step(generated_notes, response_step)
                )
                response_pitch = choose_voice_pitch(
                    "pipa",
                    user_pitch,
                    response_candidates,
                    {user_pitch, chosen_pitch},
                    chosen_pitch,
                    lower_bound_midi=(
                        pitch_index_to_midi(selected_voice_pitches["guqin"])
                        if "guqin" in selected_voice_pitches
                        else None
                    ),
                    same_step_pitches=response_same_step_pitches,
                )
                if response_pitch is None:
                    continue
                previous_voice_pitches["pipa"] = response_pitch
                generated_notes.append(
                    {
                        "id": f"ai_pipa_{response_step}_{response_pitch}_{random.randint(1000, 9999)}",
                        "step": response_step,
                        "pitch": response_pitch,
                        "duration": 1,
                        "voice": "pipa",
                    }
                )

    return enforce_guqin_rhythm(generated_notes, melody_by_step)


def decode_generated_notes(token_strs, prompt_token_count: int, lead_notes=None):
    step_candidates = parse_generated_pitch_candidates(token_strs, prompt_token_count)
    if lead_notes:
        return arrange_silk_road_tracks(lead_notes, step_candidates)

    generated_notes = []
    previous_voice_steps: Dict[str, Set[int]] = {voice: set() for voice in DUNHUANG_TRACK_VOICES}
    voice_by_inst: Dict[int, str] = {}
    generated_token_strs = token_strs[prompt_token_count:]
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

        if current_inst not in voice_by_inst:
            voice_by_inst[current_inst] = DUNHUANG_TRACK_VOICES[len(voice_by_inst) % len(DUNHUANG_TRACK_VOICES)]
        voice = voice_by_inst[current_inst]
        step = max(0, min(TOTAL_STEPS - 1, int(round(current_offset / POS_PER_STEP))))
        if step in previous_voice_steps[voice]:
            continue
        previous_voice_steps[voice].add(step)
        pitch = midi_to_pitch_index(value)
        range_min, range_max = VOICE_PITCH_RANGES[voice]
        pitch = max(range_min, min(range_max, pitch))
        if voice == "guqin" and step in DRONE_STEPS:
            pitch = nearest_consonant_stable_pitch("guqin", pitch, pitches_sounding_at_step(generated_notes, step))
        else:
            same_step_pitches = pitches_sounding_at_step(generated_notes, step)
            pitch = choose_voice_pitch(
                voice,
                pitch,
                [pitch],
                set(),
                None,
                lower_bound_midi=None,
                same_step_pitches=same_step_pitches,
            ) or pitch
        generated_notes.append(
            {
                "id": f"ai_{voice}_{step}_{pitch}_{random.randint(1000, 9999)}",
                "step": step,
                "pitch": pitch,
                "duration": 1 if voice == "pipa" else (4 if voice == "guqin" and step in DRONE_STEPS else 2),
                "voice": voice,
            }
        )
        collected_any = True

    return generated_notes


def arrange_harmony_notes(user_melody, step_candidates):
    if not user_melody:
        return []

    melody_by_step: Dict[int, Set[int]] = {}
    for melody_note in user_melody:
        melody_step = max(0, min(TOTAL_STEPS - 1, int(round(melody_note.get("step", 0)))))
        melody_duration = max(1, int(round(melody_note.get("duration", 1))))
        melody_pitch = read_pitch_index(melody_note)
        for active_step in range(melody_step, min(TOTAL_STEPS, melody_step + melody_duration)):
            melody_by_step.setdefault(active_step, set()).add(melody_pitch)

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
        same_step_pitches = {user_pitch} | pitches_sounding_at_step(generated_notes, step)

        guqin_pitch = choose_voice_pitch(
            "guqin",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["guqin"],
            lower_bound_midi=None,
            same_step_pitches=same_step_pitches,
        )
        if guqin_pitch is not None:
            selected_voice_pitches["guqin"] = guqin_pitch
            used_pitches.add(guqin_pitch)
            same_step_pitches.add(guqin_pitch)

        guqin_midi = pitch_index_to_midi(guqin_pitch) if guqin_pitch is not None else None
        pipa_pitch = choose_voice_pitch(
            "pipa",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["pipa"],
            lower_bound_midi=guqin_midi,
            same_step_pitches=same_step_pitches,
        )
        if pipa_pitch is not None:
            selected_voice_pitches["pipa"] = pipa_pitch
            used_pitches.add(pipa_pitch)
            same_step_pitches.add(pipa_pitch)

        pipa_midi = pitch_index_to_midi(pipa_pitch) if pipa_pitch is not None else guqin_midi
        xiao_pitch = choose_voice_pitch(
            "xiao",
            user_pitch,
            candidate_pitches,
            used_pitches,
            previous_voice_pitches["xiao"],
            lower_bound_midi=pipa_midi,
            same_step_pitches=same_step_pitches,
        )
        if xiao_pitch is not None:
            selected_voice_pitches["xiao"] = xiao_pitch
            used_pitches.add(xiao_pitch)
            same_step_pitches.add(xiao_pitch)

        for voice in DUNHUANG_TRACK_VOICES:
            chosen_pitch = selected_voice_pitches.get(voice)
            if chosen_pitch is None:
                continue
            previous_voice_pitches[voice] = chosen_pitch
            duration = clamp_duration_to_consonant_steps(
                chosen_pitch,
                step,
                max(1, min(TOTAL_STEPS - step, int(round(note.get("duration", 1))))),
                melody_by_step,
            )
            generated_notes.append(
                {
                    "id": f"ai_{voice}_{step}_{chosen_pitch}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": chosen_pitch,
                    "duration": duration,
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
        generated_notes = decode_generated_notes(
            generated_token_strs,
            len(prompt_token_strs),
            transformed_lead_notes,
        )
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

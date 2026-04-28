import os
import random
import sys
from pathlib import Path

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
        diff = abs(midi_pitch - candidate_midi)
        if diff < best_diff:
            best_diff = diff
            best_pitch_index = pitch_index
    return best_pitch_index


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


def decode_generated_notes(token_strs, prompt_token_count: int):
    generated_token_strs = token_strs[prompt_token_count:]
    inst_notes = {}
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

        inst_notes.setdefault(current_inst, []).append((current_offset, value))
        collected_any = True

    if not inst_notes:
        return []

    generated_notes = []
    seen_notes = set()
    for inst_index, inst_id in enumerate(sorted(inst_notes)):
        voice = GENERATED_VOICES[min(inst_index, len(GENERATED_VOICES) - 1)]
        for offset, midi_pitch in sorted(inst_notes[inst_id], key=lambda item: (item[0], item[1])):
            step = max(0, min(TOTAL_STEPS - 1, int(round(offset / POS_PER_STEP))))
            pitch_index = midi_to_pitch_index(midi_pitch)
            note_key = (voice, step, pitch_index)
            if note_key in seen_notes:
                continue
            seen_notes.add(note_key)
            generated_notes.append(
                {
                    "id": f"ai_{voice}_{step}_{pitch_index}_{random.randint(1000, 9999)}",
                    "step": step,
                    "pitch": pitch_index,
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
        generated_notes = decode_generated_notes(generated_token_strs, len(prompt_token_strs))
        print(f"GPU 推理成功，返回 {len(generated_notes)} 个音符。")
        return {"status": "success", "generated_notes": generated_notes}
    except Exception as exc:
        print(f"GPU 推理过程中出错: {exc}")
        raise HTTPException(status_code=500, detail=f"GPU 推理失败: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

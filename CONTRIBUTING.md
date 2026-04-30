# Contributing to Lingyan Studio

Thanks for helping tune Lingyan Studio. This project has two main surfaces:

- React/Vite frontend for score editing, playback, recording, and AI requests.
- FastAPI/Museformer backend for generation and harmony post-processing.

## Local Frontend Setup

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

Before opening a pull request, run:

```bash
npm run lint
npm run build
```

## Backend And Model Notes

The backend entrypoint is `server/museformer_api.py`.

The live service expects Museformer and MuseCoco paths to exist on the model server. For local work without the model weights, focus on the pure post-processing functions:

- `parse_generated_pitch_candidates`
- `get_step_candidate_pitches`
- `choose_voice_pitch`
- `arrange_harmony_notes`

These functions are the safest starting point for improving musicality without changing the model loading path.

## Music Quality Workflow

Use `docs/music-eval-cases.md` as the shared listening and regression checklist.

For each tuning change, record:

- Which melody cases you tested.
- What improved in alto, tenor, and bass behavior.
- Any case that became worse.
- Whether the result changes density, range, cadence, or voice independence.

Good tuning pull requests should be small enough to listen to and review. Prefer one musical goal per PR, such as bass motion, cadence stability, avoiding doubled soprano, or smoother inner voices.

## Branch Names

Use descriptive branches:

- `feature/midi-export`
- `fix/recording-error-message`
- `tuning/bass-motion`
- `tuning/cadence-stability`

## Pull Requests

Include the checks from `.github/pull_request_template.md`.

If a change touches music generation, include a short before/after note instead of only describing the code. Musical behavior is part of the contract.

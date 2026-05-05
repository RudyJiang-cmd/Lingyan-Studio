# Changelog

## 2026-05-05

- Replaced the public site entry with the new mobile-first Dunhuang interaction flow.
- Added the `dunhuang.html` mobile prototype entry and routed the root `index.html` to the same experience for production deployment.
- Added humming and preset input flow, BPM 120 count-in/recording simulation, pitch preview, quartet score animation, browser synthesis playback, and survey/finish pages.
- Connected the mobile composition stage to the same-origin `/api/generate` Museformer backend path, with strict failure handling: backend failures show an explicit error and never create fake accompaniment tracks.
- Kept compatibility with legacy backend voices `alto` / `tenor` / `bass` by mapping them to `xiao` / `pipa` / `guqin` in the mobile score.
- Configured local Vite development proxy for `/api` to the Tencent Cloud Museformer backend `43.129.24.82:8000`.

## 2026-05-04

- Added a V0 natural-language style control path: frontend requests now send `style_prompt` plus structured controls to the Museformer API.
- Added backend control normalization for Dunhuang style, rhythmic profiles, density, bass motion, cadence strength, and percussion toggles.
- Added Dunhuang quartet post-processing output voices: `xiao`, `pipa`, `guqin`, and optional `percussion`, while retaining the legacy `alto` / `tenor` / `bass` path.
- Added frontend playback/rendering compatibility for the new Dunhuang track voices.
- Documented that natural language is translated into structured controls before post-processing; it is not passed directly into Museformer as text.

## 2026-04-30

- Restored the score editor to a stable four-measure quarter-note input model.
- Added responsive score spacing so all four measures and the final barline remain visible across browser widths.
- Added automatic note-duration stretching before playback and AI harmony generation: notes sustain to the next note in the same measure, or to the measure end.
- Added duration-aware note glyphs: quarter notes use filled heads with stems, longer notes use open heads, and full-measure notes omit stems.
- Preserved generated duration data through the AI request and Museformer backend prompt path.
- Kept rests and sub-quarter durations out of the editing workflow to avoid confusing player input.
- Migrated the documented public preview host to `119.45.228.209`, a monthly/yearly Tencent Cloud server prepared for ICP filing.
- Routed MuseFormer API calls through same-origin `/api/generate`; the frontend Nginx proxy now targets the backend EIP `43.129.24.82`.

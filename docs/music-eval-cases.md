# Music Quality Eval Cases

Use these melodies as a lightweight regression set when tuning `server/museformer_api.py`.

The `pitch` index follows the frontend grid: lower numbers are visually higher, and higher numbers are visually lower. All examples use 16 steps.

## Case 1: Descending Phrase

```json
[
  { "step": 0, "pitch": 14 },
  { "step": 4, "pitch": 12 },
  { "step": 8, "pitch": 10 },
  { "step": 12, "pitch": 9 }
]
```

Listen for:

- Bass should not sit on one repeated pitch for the whole phrase.
- Inner voices should avoid moving in lockstep with the soprano.
- The final sonority should feel more settled than the middle steps.

## Case 2: Short Neighbor Motion

```json
[
  { "step": 0, "pitch": 14 },
  { "step": 2, "pitch": 13 },
  { "step": 4, "pitch": 14 },
  { "step": 6, "pitch": 12 },
  { "step": 8, "pitch": 10 }
]
```

Listen for:

- Alto and tenor should prefer small motion when the melody moves by step.
- Generated voices should avoid duplicating the user pitch at the same step.
- The harmony should not become too dense on every short note.

## Case 3: Sparse Motif

```json
[
  { "step": 0, "pitch": 14 },
  { "step": 8, "pitch": 10 }
]
```

Listen for:

- Generated voices should fill enough space to feel intentional.
- Bass should outline a direction instead of only mirroring the same target interval.
- The second event should answer the first rather than sounding unrelated.

## Case 4: High Register Melody

```json
[
  { "step": 0, "pitch": 7 },
  { "step": 4, "pitch": 6 },
  { "step": 8, "pitch": 5 },
  { "step": 12, "pitch": 3 }
]
```

Listen for:

- Alto should stay below the melody without collapsing into tenor.
- Tenor and bass should remain distinguishable in playback.
- Large leaps should be rare unless they create a clear cadence or register reset.

## Case 5: Cadence Check

```json
[
  { "step": 0, "pitch": 12 },
  { "step": 4, "pitch": 10 },
  { "step": 8, "pitch": 9 },
  { "step": 12, "pitch": 14 }
]
```

Listen for:

- The last step should feel like an arrival.
- Bass should support the ending instead of choosing an arbitrary nearby pitch.
- Inner voices should reduce restless motion at the final event.

## Review Notes Template

```text
Branch:
Backend commit:
Cases tested:
Improved:
Regressed:
Next tuning idea:
```

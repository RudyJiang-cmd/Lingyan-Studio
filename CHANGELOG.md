# Changelog

## 2026-04-30

- Restored the score editor to a stable four-measure quarter-note input model.
- Added responsive score spacing so all four measures and the final barline remain visible across browser widths.
- Added automatic note-duration stretching before playback and AI harmony generation: notes sustain to the next note in the same measure, or to the measure end.
- Added duration-aware note glyphs: quarter notes use filled heads with stems, longer notes use open heads, and full-measure notes omit stems.
- Preserved generated duration data through the AI request and Museformer backend prompt path.
- Kept rests and sub-quarter durations out of the editing workflow to avoid confusing player input.
- Migrated the documented public preview host to `119.45.228.209`, a monthly/yearly Tencent Cloud server prepared for ICP filing.

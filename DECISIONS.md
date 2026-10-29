# Decisions

Team decisions that affect this repository, with the date and where they are applied. Code and prompt changes are in `CHANGELOG.md`.

## 2026-10-29, team meeting

1. **One response scale for every scale in the survey.** AI-generated items are fielded with Edmondson's 7-point scale, 1 = very inaccurate to 7 = very accurate, the same as the validated items, so response format is not a difference between scales.
   - Applied to the Stage 1 survey: the scale already drawn (`gpt-6-astra|L0|run5`) is kept. It is not regenerated or redrawn. Its item wording is unchanged; only the response scale it is fielded with changes. Its prompt (version 3) named a strongly disagree to strongly agree scale, and `selected_scales.md` states this.
   - Applied going forward: `prompts.json` version 4 names Edmondson's scale in the prompt, so scales generated from now on are written for it. `select_scales.py` prints the survey's response scale from `prompts.json` and flags any drawn scale whose prompt named a different one.
2. **Stage 1 uses the version 3 runs.** The 60 scales in `log.jsonl` (version 3) and the draw from them stay the Stage 1 data. Version 4 applies to runs after the Stage 1 submission.
3. **Survey layout.** The validated items and the drawn AI items are combined in one survey, mixed into one list, with items on similar content placed near each other.

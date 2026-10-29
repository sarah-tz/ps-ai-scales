# Changelog

Record every change to the code or prompts here, with the date and the reason. After the protocol is frozen, a change to `prompts.json` needs a version bump and recorded approval.

## 2026-10-28, handover (cloud session)

- Created `prompts.json` (version 1), `generate_scales.py`, `PROTOCOL.md` and supporting files.
- Tested with the fake model only: full grid, resume, retry rule, `--levels` filter.
- Not tested: any real API call.

## Frozen protocol commit

- 2026-10-29: commit `ae80ae106287aa18fa8140190856ccec6bf35706`, protocol and `prompts.json` version 4. It applies to runs after the Stage 1 submission. The Stage 1 data (`log.jsonl`) and draw were generated under version 3 and are kept (see `DECISIONS.md`).
- 2026-10-28: commit `7403e51021c23bad8b35b4c5e4dfdcbce48defd4`, protocol and `prompts.json` version 3. It replaced version 2 below.
- 2026-10-28: commit `74355f336ded1dc475cc534ca1ee09cf66f0d325`, protocol and `prompts.json` version 2. Log rows record the commit checked out at run time in `script_commit`. Later commits that touch only documentation (such as this entry) leave the code and prompts identical to this commit, and each row's `prompt_file_hash` confirms the prompts. Any change after this commit needs a version bump, an entry below and recorded approval.

## Changes after handover

(Add entries below.)

### 2026-10-28, run setting: `--max-tokens 16000` for Anthropic runs

- All real Anthropic runs (smoke test and full run) use `--max-tokens 16000` instead of the script default of 1500. No code changed; the value is passed on the command line and recorded in each log row under `sampling.max_tokens`.
- Reason: per Anthropic's documentation, current Claude models think before answering and that thinking counts toward `max_tokens`, so 1500 risked cutting off the list of items. The value is a ceiling only; cost depends on tokens actually used.

### 2026-10-28, tests: parser checked against real model output

- Added two tests to `tests/test_parse.py` using the stage 1 and stage 2 replies from the first real smoke test (`claude-opus-5-5`, L0, run 1), copied verbatim. The stage 2 reply has a bold heading, a bullet-point review, the numbered list and a closing sentence; the parser returns exactly the 7 numbered items for both.
- `parse_items` itself was not changed.

### 2026-10-28, logging: record every setting and the exact request (approved)

Goal: anyone rerunning the script goes through the same process and can see exactly what was sent.

- `generate_scales.py`: each log row now also records `request` (endpoint, headers without the API key, full JSON body), `run_settings` (runs, levels, seed, max_tokens, pause, retry count, API version), `environment` (Python version and OS, no user or machine name), `run_order_position`, `provider_response_id` and `provider_request_id`. Failed calls keep their request too.
- `sampling` now names every setting, and records unsent ones (temperature, thinking, effort) as "not sent (provider default)". What is sent to the API is unchanged.
- `--max-tokens` default changed from 1500 to 16000, so the default command matches the study runs.
- If the API key variable is not set, the script asks for the key with a hidden prompt instead of stopping. The key stays in memory for that run only.
- HTTP timeout raised from 120 to 600 seconds, since replies may now be long. [Inference] 120 seconds could be too short at the higher token limit.
- `tests/test_logging.py`: checks that the key never appears in what is logged, that the request and response IDs are recorded, and that a fake-model run writes the run settings.
- `PROTOCOL.md`: retry rule now states what happens on a failed call; log schema lists the new fields. `README.md`: run instructions updated, plus the macOS certificate note.
- Rows in `test_smoke.jsonl` were written before this change and lack the new fields. It is a test file.

### 2026-10-28, prompts version 2, parser and format check (approved)

Found in the second smoke test (`test_smoke_v2.jsonl`): the stage 2 reply numbered its review notes 1 to 7 before the revised list, so the parser counted 14 items and marked a usable reply invalid, which triggered a retry.

- `prompts.json` version 1 to 2. Revision text, last sentence: "Then return a revised list of exactly 7 items in the same format." became "Then return only a numbered list of exactly 7 revised items." This matches the stage 1 wording ("Return only a numbered list"). Cost: the written review is no longer requested, so the reasons for changes are not in the reply. Nothing else in the prompts changed.
- `parse_items` now returns the last numbered list in a reply (a list starts where numbering returns to 1). Replies with one list parse as before.
- New log field `format_check`: "exact" if the reply is only a list numbered 1 to 7, otherwise "deviation" with the reason. It flags any shape other than the expected one, including kinds of failure not seen so far. It does not affect validity or retries.
- Tests added for both, using the real reply above. `PROTOCOL.md` updated (run procedure step 4, log schema).

### 2026-10-28, selection rule for the Stage 1 submission (decided)

- `PROTOCOL.md`: new section "Selection for the Stage 1 submission". One AI scale is drawn at random (seed 20261028) from all valid stage 1 scales of the models run by then (Anthropic and OpenAI), only after both have run. The 6-scale balanced draw stays for the full study.
- New `select_scales.py`: builds the pool (valid stage 1 rows, one per combination, sorted by ID), draws with the seed, and writes `selected_scales.csv` and `selected_scales.md` recording the seed, pool size, models and log hash. Written before any real run, so the rule is fixed in advance.
- New `tests/test_select.py`: pool contains only valid stage 1 scales; same seed gives the same draw and different seeds give different draws; output files record the seed.

### 2026-10-28, version 3: two fixes from code review (approved)

A fresh read of the version 2 code found two bugs, both confirmed with tests. No study data existed yet, so no data is affected.

- Cut-off replies: a reply that stopped partway through item 7 (for example at the length limit) still had 7 numbered lines and was counted valid and "exact". `valid` now also requires the model to report that it finished the reply itself (`finish_reason` `end_turn` or `stop`). Otherwise the reply is invalid and gets the usual single retry.
- Failed stage 2 on re-run: if both stage 2 attempts failed with an error, a re-run treated the combination as done. Now only a stage 2 row without an error counts as done, matching how failed stage 1 calls are handled.
- `prompts.json` version 2 to 3. The prompt text is unchanged; the version records the rule change. `PROTOCOL.md` retry rule updated.
- `tests/test_logging.py`: tests for both fixes. 21 tests pass.
- Not changed yet: `PROTOCOL.md` still says the local model gets a recorded seed, which the code does not do. To be corrected when the open-weight model is set up.

### 2026-10-28, pool report (new analysis code; no change to prompts or run logic)

- New `analyze_pool.py`: reads `log.jsonl` and `reference/items.md`, writes `pool_report.csv` (one row per scale and stage) and `pool_summary.md`. Counts negatively worded items with a labelled word heuristic and measures lexical overlap (Jaccard on content words) with the Edmondson and May items. Method and limits are in the script header and the summary.
- New `tests/test_pool.py`.
- The protocol version is unchanged: this script only reads the log and does not affect generation or the scale draw.

### 2026-10-29, version 4: Edmondson's response scale in the prompt (approved)

Decided after the team meeting: AI items and Edmondson's items should share one response format in the survey, so the format is not a difference between scales.

- `prompts.json` version 3 to 4. Task text: "Respondents will rate their agreement with each item on a 7-point scale (1 = strongly disagree, 7 = strongly agree)." became "Respondents will rate each item on a 7-point scale (1 = very inaccurate, 7 = very accurate)." These are the end labels of Edmondson's scale as recorded in `reference/items.md`. New field `response_scale` holds the same text. Nothing else in the prompts changed.
- `select_scales.py` now prints the response scale from `prompts.json` instead of fixed "strongly disagree / strongly agree" text.
- Tests: the task text contains `response_scale`, and the selection file prints it.
- `PROTOCOL.md`: design table and rationale updated.
- Version 3 outputs (log, draw, pool report) moved unchanged to `archive/v3/`, with a note. They were written for the old response format; the study uses a new version 4 pool. Not replaced because of their content or results.

### 2026-10-29, survey response scale applied without regenerating (approved)

Follows the 2026-10-29 team meeting decision recorded in `DECISIONS.md`: every scale in the survey is fielded with Edmondson's 7-point scale (1 = very inaccurate, 7 = very accurate).

- Corrects the version 4 entry above: the version 3 outputs were moved back from `archive/v3/` to their original places, unchanged (`log.jsonl` SHA-256 `a77dc13...`, as recorded in the draw). The archive note was removed. No API calls were made and no scale was regenerated or redrawn.
- `select_scales.py`: prints the survey's response scale from `prompts.json`, states the scale named in the prompt that generated each drawn scale (read from the log), and notes when they differ. Item wording is never changed.
- `selected_scales.md` and `.csv` rebuilt from the same log and seed: the same scale (`gpt-6-astra|L0|run5`) and the same items; the CSV is byte-identical. Only the response-scale lines in the .md changed.
- `PROTOCOL.md`: the survey response-scale rule added to "Selection for the Stage 1 submission". New `DECISIONS.md` records the meeting decisions. Test added for the scale note.
- Four smoke-test calls were made under version 4 before this correction (test files, not committed).

### 2026-10-29, simulation folder added (no change to prompts or run logic)

- New `simulation/`: the multi-scale simulation and power analysis written by a teammate, copied from the team workspace at commit `e5d3056274b502a232b6f87b1f6eda99d376b72b` so the project lives in one folder. `multiscale_sim.py`, `requirements.txt` and every file in `simulation/results/` are byte-identical to that commit.
- One edit: the "Reproduce" commands in `simulation/results/MULTISCALE.md` now use the paths of this folder (`simulation/requirements.txt`, `--out simulation/results`, run from the top folder).
- `README.md`: the simulation is listed under Files and as run step 8.
- The simulation uses hypothetical parameters only and does not read `log.jsonl`, so the protocol version is unchanged. It needs numpy, scipy and matplotlib; the generation code stays standard library only.
- The text of the teammate's README was not copied. Its description of a 20-scale draw from a pool of 60 does not match `PROTOCOL.md` and is still to be settled with the team.

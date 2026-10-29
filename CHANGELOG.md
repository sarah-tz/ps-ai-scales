# Changelog

Record every change to the code or prompts here, with the date and the reason. After the protocol is frozen, a change to `prompts.json` needs a version bump and recorded approval.

## 2026-10-28, handover (cloud session)

- Created `prompts.json` (version 1), `generate_scales.py`, `PROTOCOL.md` and supporting files.
- Tested with the fake model only: full grid, resume, retry rule, `--levels` filter.
- Not tested: any real API call.

## Frozen protocol commit

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

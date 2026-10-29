# Protocol for generating AI psychological safety scales

Status: frozen, version 4 (matches `prompts.json` version 4; see `CHANGELOG.md` for the commit). Design choices below are judgments, not tested results. Model behavior is not assured to repeat across runs or over time.

## Purpose

The study asks how much conclusions about psychological safety change when it is measured with AI-generated scales instead of a validated one, and how much AI-generated scales vary across models, prompts and runs. This protocol covers only the step that produces the AI scales.

## Design

Full design: 4 models x 3 information levels x 5 runs = 60 first-pass scales, plus one scripted revision of each, for 120 scales.

| Factor | Levels | Held fixed |
| --- | --- | --- |
| Model | Three vendor flagships and one open-weight model run on a machine the team controls. Exact model ID recorded on the day. | Fresh conversation per run, no system prompt, no memory or personalization |
| Information level | L0 construct name only. L1 adds Edmondson's definition. L2 adds her boundaries (not cohesiveness, beyond trust). | Output format: 7 items, 7-point scale from "very inaccurate" to "very accurate" (Edmondson's response labels), items about "this team" |
| Refinement | Stage 1 first output. Stage 2 one scripted revision in the same conversation. | The revision text is identical for every run |
| Runs | 5 per model and level | Provider default sampling settings, recorded. Local model gets a recorded seed. |

Why 7 items and a 7-point scale labelled "very inaccurate" to "very accurate": they match Edmondson's psychological safety scale, so differences in item content are not confounded with length or response format. Version 3 used "strongly disagree" to "strongly agree"; version 4 changed this so AI and validated items share one response format in the survey.

Why no example items: Edmondson's items are public and may be in the models' training data. We measure overlap with her items and May et al.'s items afterwards, and report it, rather than prompting for it.

## Design answers

| Question | Decision | Reason |
| --- | --- | --- |
| Which AI | Four models: three vendors, one open-weight | Between-model spread is part of the research question. Open-weight gives a reproducible baseline. |
| Multiple prompts | Three information levels, nothing else varies | Differences can be attributed to how much construct information the model gets. |
| How much to share | Only construct information from Edmondson's text | Keeps AI scales independent of the validated scales and of our hypotheses. |
| One message or refinement | Both, logged separately | Single shot is cleanest. A fixed scripted revision stands in for expert coaching without human judgment. |
| Rounds | One scripted revision, then stop | More rounds add drift and cost. No evidence supports a higher number. |
| Runs | 5 per cell | Gives a spread within each cell. |
| Interface | API or local model, fresh context each run | Chat apps can carry memory or hide settings. |

## Prompts

The exact text is in `prompts.json`. Every prompt is the construct block for its level, then the task text. The stage 2 revision text is the same for all runs. Do not tell the model to include reverse-worded items. Whether it does is an outcome to report.

## Run procedure

1. Freeze the protocol: commit `prompts.json`, the script and this file. Note the commit hash. Get sign-off on the model list.
2. Dry run: one model, level L0, one run, both stages. Check the log row is complete.
3. Run order for all combinations is shuffled with a recorded seed.
4. For each combination: fresh conversation, stage 1 prompt, save the raw reply, send the stage 2 text in the same conversation, save, parse the 7 items. The items are taken from the last numbered list in the reply (a list starts where numbering returns to 1). Each reply also gets a format check: "exact" if it contains only a list numbered 1 to 7, otherwise "deviation" with the reason. The check does not change validity or trigger a retry. Every deviation is listed in the pool report and read by eye against its raw reply to confirm the extracted items, and the deviation rate is reported per model.
5. Do not edit outputs. Do not skip or redo a run because the result looks poor.
6. Retry rule: a reply is valid only if it contains exactly 7 items and the model reports that it finished the reply itself (finish reason `end_turn` or `stop`), so a reply cut off by a length limit or a refusal is invalid even if 7 numbered lines are present. If a reply is invalid, repeat the identical call once. Log both attempts. Report the invalid rate. A call that fails with an error (network or API) returns no items, so it counts as invalid and gets the same single retry. If both stage 1 attempts fail with no text, stage 2 is not sent; running the script again repeats that combination, because only combinations with a stage 2 reply are skipped. The same applies when both stage 2 attempts fail with an error: a re-run repeats the combination. This re-run is for technical failures only, and the failed attempts stay in the log.
7. Commit after each batch. Check for personal information first.
8. Fallback without API keys: temporary chat, memory and personalization off, interface recorded as "chat". Settings are hidden in chat apps, and a model alias may point to a newer version over time, so state this limitation.

## Log schema

One row per model response, JSON lines. Fields: combination_id, run_number, run_order_position, timestamp_utc, operator, provider, model_requested, model_id_returned, interface, sampling, request, stage, information_level, prompt_file_hash, prompt_text, context, raw_response, parsed_items, valid, format_check, is_retry, attempt, usage, finish_reason, provider_response_id, provider_request_id, error, script_commit, protocol_version, run_settings, environment.

- `request` is the exact call: endpoint, headers (the API key header is left out) and the full JSON body, including the whole message history sent.
- `sampling` names every setting and says whether it was sent. Settings the script does not send (temperature, thinking, effort) are recorded as "not sent (provider default)".
- `run_settings` holds the run's options: runs, levels, seed, max_tokens, pause, retry count and API version.
- `environment` holds the Python version and operating system, with no user or machine name.

## Choosing scales for the survey

The survey cannot carry 120 scales, so a small set goes to participants. The rule is set before anyone sees results, because choosing the scale that looks best would repeat the measurement-stage flexibility the project studies.

1. Describe the whole pool first, without people: item overlap with Edmondson's and May's items, number of reverse-worded items, and valid-output rate.
2. Draw 6 stage-1 scales at random with a recorded seed, balanced so every model appears at least once and every information level appears twice. Do not use quality, fit or expected results.
3. Field the stage-1 versions. Stage 2 revisions are analyzed by text properties and simulated responses only, unless the group decides otherwise.
4. Survey length: Edmondson's 7 items, May's 3 items and 6 AI scales of 7 items is 52 scale items before the learning behavior, efficacy and open-ended questions. If that is too long, each participant could see the validated scales plus 3 randomly chosen AI scales. The team decides.

### Selection for the Stage 1 submission

For the Stage 1 submission the survey uses one AI scale, drawn from the models run by then (Anthropic and OpenAI, 5 runs x 3 levels each). The draw happens only after both models have run.

1. Pool: every valid stage 1 scale in `log.jsonl`, one per combination, sorted by combination ID.
2. Draw 1 scale uniformly at random with `select_scales.py`, seed 20261028. Nothing about item content, overlap or quality is used.
3. The output file records the seed, the pool size, the models in the pool and the SHA-256 hash of the log, so anyone can repeat the draw.

The 6-scale balanced draw above applies to the full study, after all four models have run.

Response scale in the survey: every scale is fielded with Edmondson's 7-point scale (1 = very inaccurate, 7 = very accurate), as decided on 2026-10-29 (`DECISIONS.md`). The Stage 1 pool was generated under version 3, whose prompt named a strongly disagree to strongly agree scale; the drawn scale keeps its wording and is fielded with Edmondson's scale. From version 4 the prompt names Edmondson's scale, so later pools are generated for the scale they are fielded with.

## Minimum version for the Nov 1 submission

One model, 5 runs, 3 levels (30 calls), or the 54-scale version across three models if time allows. The full grid runs after the proposal is in.

## Open decisions for the group

- Which three vendor models and which open-weight model.
- Open-weight or self-hosted as the reproducible baseline, and who provides the machine or access.
- Who holds API accounts and pays. [Unverified] cost.
- Field only stage 1 scales, or the revisions too.
- Six scales for every participant, or three each.
- How to state in the proposal that Claude helped design this protocol and may also be one of the models.

# AI scale generation (psychological safety)

Generates AI-written psychological safety scales and logs every call. It follows `PROTOCOL.md`.

## Files

- `prompts.json`: the exact prompt text. Do not edit after the protocol is frozen. Its hash is logged with every call.
- `generate_scales.py`: runs one model across 3 information levels x N runs, each with a stage 1 reply and a stage 2 scripted revision. Python 3 standard library only.
- `reference/items.md`: items of the validated scales, used for the overlap analysis.
- `log.jsonl`: created on first run. One JSON row per model response, including retries.

## Run (from this folder)

1. Test with no API and no cost:
   `python3 generate_scales.py --provider mock --model mock-1 --runs 2 --out test_run.jsonl --pause 0`
   The output file is fake. Delete it afterwards.

2. Smoke test with one real call pair (cheap):
   `python3 generate_scales.py --provider anthropic --model <exact model id> --levels L0 --runs 1 --out test_smoke.jsonl`
   If `ANTHROPIC_API_KEY` is not set, the script asks for the key with a hidden prompt. It is kept in memory for that run only. Use `--provider openai` and `OPENAI_API_KEY` for an OpenAI-style endpoint.

3. Full run for one model (3 levels x 5 runs x 2 stages = 30 calls):
   `python3 generate_scales.py --provider <provider> --model <exact model id> --runs 5 --out log.jsonl`

4. A locally hosted open-weight model with an OpenAI-style endpoint:
   `export OPENAI_BASE_URL=http://localhost:8000/v1` and `export OPENAI_API_KEY=anything`, then `--provider openai` with the model name your server uses.

5. To add another model, run again with its provider and model ID and the same `--out`. Combinations already logged for that model are skipped.

6. Draw the scale for the survey, after all models for the draw have run:
   `python3 select_scales.py --log log.jsonl --n 1`
   This writes `selected_scales.md` (ready to paste into a survey tool) and `selected_scales.csv`, with the seed recorded. See `PROTOCOL.md`, "Choosing scales for the survey".

7. Describe the pool (valid rate, negatively worded items, overlap with the validated items):
   `python3 analyze_pool.py`
   This writes `pool_report.csv` (one row per scale and stage) and `pool_summary.md`. The method and its limits are in the script header and the summary.

## Notes

- Order is shuffled with a recorded seed (`--seed`).
- If a reply is invalid (not exactly 7 items, cut off before the model finished, or an error), the same call is repeated once. Both attempts are logged. Nothing is regenerated for any other reason.
- Sampling settings are the provider defaults and the log says so. `--max-tokens` defaults to 16000, the value used for the study runs.
- Each log row holds the exact request sent (without the key), the run settings and the Python version, so a run can be repeated with the same command.
- On macOS with Python from python.org, run "Install Certificates.command" in the Python folder under Applications once, or HTTPS calls fail with `CERTIFICATE_VERIFY_FAILED`.
- Never commit API keys. Check the log has no personal information before committing.
- The repository is reviewed double-blind. Do not put names in files. The `operator` field defaults to "anon".
- The Anthropic and OpenAI calls follow the providers' published request formats but were not tested against the live services when written. The first real call is the test.

## Tests

`python3 -m unittest discover -s tests`

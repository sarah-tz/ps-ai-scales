#!/usr/bin/env python3
"""Generate AI psychological safety scales and log every call.

One invocation runs one model across all information levels and runs, for
both stage 1 (first output) and stage 2 (scripted revision in the same
conversation). Run it again with another model to add to the same log.

Standard library only. API keys are read from environment variables, or
asked for with a hidden prompt if the variable is not set. Keys are never
written to the log or to any file.

  ANTHROPIC_API_KEY             for --provider anthropic
  OPENAI_API_KEY                for --provider openai
  OPENAI_BASE_URL (optional)    for any OpenAI-compatible endpoint, for
                                example a locally hosted open-weight model

Every log row records the exact request sent (endpoint, headers without the
key, and the full JSON body), the settings of the run, and the provider's
response and request IDs, so the call can be repeated as it was made.

Examples
  python generate_scales.py --provider mock --model mock-1 --runs 2
  python generate_scales.py --provider anthropic --model <model-id> --runs 5
  python generate_scales.py --provider openai --model <model-id> --runs 5
"""
import argparse
import getpass
import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT_FILE = HERE / "prompts.json"
ANTHROPIC_VERSION = "2023-06-01"
NOT_SENT = "not sent (provider default)"
KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
# Finish reasons that mean the model ended its reply itself. Anything else
# (for example max_tokens, length, refusal) means the reply may be cut off.
FINISHED = {"end_turn", "stop"}


# ---------------------------------------------------------------- helpers
def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else "not-a-git-repo"
    except Exception:
        return "git-unavailable"


NUMBERED = re.compile(r"^\s*(?:\*\*)?(\d{1,2})[.)]\s*(.+?)\s*$")


def parse_items(text):
    """Return the items of the last numbered list in a model reply.

    A new list starts wherever the numbering goes back to 1, so numbered
    notes written before the final list are not counted as items.
    """
    lists = []
    for line in text.splitlines():
        m = NUMBERED.match(line)
        if m:
            if m.group(1) == "1" or not lists:
                lists.append([])
            lists[-1].append(m.group(2).strip().strip("*").strip())
    return lists[-1] if lists else []


def format_check(text, n_items):
    """'exact' if the reply is only a list numbered 1 to n_items, else 'deviation: <reasons>'.

    It does not try to recognise kinds of failure; anything other than the
    expected shape is flagged, so the reply can be checked by eye.
    """
    numbers, other = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        m = NUMBERED.match(line)
        if m:
            numbers.append(int(m.group(1)))
        else:
            other += 1
    reasons = []
    if other:
        reasons.append(f"{other} line(s) of text outside the list")
    if numbers != list(range(1, n_items + 1)):
        reasons.append(f"numbered lines are {numbers}, expected 1 to {n_items}")
    return "exact" if not reasons else "deviation: " + "; ".join(reasons)


def ensure_key(var):
    """Make sure the API key is in the environment, asking with a hidden prompt if not."""
    if os.environ.get(var):
        return
    if not sys.stdin.isatty():
        raise SystemExit(f"Set {var} first.")
    key = getpass.getpass(f"Paste your {var} (it stays hidden), then press Return: ").strip()
    if not key:
        raise SystemExit("No key entered.")
    os.environ[var] = key  # this process only; never written to disk or the log


class CallError(Exception):
    """A failed API call, carrying the request so it can still be logged."""

    def __init__(self, message, request):
        super().__init__(message)
        self.request = request


def post_json(url, headers, body, timeout=600):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code}: {detail}")


def send(url, logged_headers, secret_headers, body):
    """POST and return (data, response headers, request record). The record leaves out secret headers."""
    request = {"url": url, "headers": logged_headers, "body": body}
    try:
        data, resp_headers = post_json(url, {**logged_headers, **secret_headers}, body)
    except Exception as e:
        raise CallError(str(e), request) from e
    return data, resp_headers, request


# ------------------------------------------------------------- providers
# Each provider takes the full message history and returns a dict with:
#   text, model_id, usage, finish_reason, sampling, request,
#   response_id, request_id
def call_anthropic(model, messages, max_tokens):
    data, resp_headers, request = send(
        "https://api.anthropic.com/v1/messages",
        {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"]},
        {"model": model, "max_tokens": max_tokens, "messages": messages},
    )
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return {
        "text": text,
        "model_id": data.get("model", model),
        "usage": data.get("usage"),
        "finish_reason": data.get("stop_reason"),
        "sampling": {
            "max_tokens": max_tokens,
            "temperature": NOT_SENT,
            "thinking": NOT_SENT,
            "effort": NOT_SENT,
            "system_prompt": "none",
        },
        "request": request,
        "response_id": data.get("id"),
        "request_id": resp_headers.get("request-id"),
    }


def call_openai(model, messages, max_tokens):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data, resp_headers, request = send(
        f"{base}/chat/completions",
        {"Content-Type": "application/json"},
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        {"model": model, "messages": messages},
    )
    choice = (data.get("choices") or [{}])[0]
    return {
        "text": (choice.get("message") or {}).get("content", "") or "",
        "model_id": data.get("model", model),
        "usage": data.get("usage"),
        "finish_reason": choice.get("finish_reason"),
        "sampling": {
            "max_tokens": NOT_SENT,
            "temperature": NOT_SENT,
            "reasoning_effort": NOT_SENT,
            "system_prompt": "none",
        },
        "request": request,
        "response_id": data.get("id"),
        "request_id": resp_headers.get("x-request-id"),
    }


def call_mock(model, messages, max_tokens):
    """Offline stand-in used only to test the pipeline. Not a real model."""
    last = messages[-1]["content"]
    stage2 = "Review the 7 items" in last
    items = [f"Mock item {i} about this team ({'revised' if stage2 else 'first'})." for i in range(1, 8)]
    if os.environ.get("MOCK_FAIL") == "1" and random.random() < 0.4:
        items = items[:5]  # simulates a wrong item count, to test the retry rule
    return {
        "text": "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1)),
        "model_id": model,
        "usage": {"mock": True},
        "finish_reason": "stop",
        "sampling": {"temperature": "n/a", "max_tokens": "n/a"},
        "request": {"url": "mock", "headers": {}, "body": {"model": model, "messages": messages}},
        "response_id": None,
        "request_id": None,
    }


PROVIDERS = {"anthropic": call_anthropic, "openai": call_openai, "mock": call_mock}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--model", required=True, help="Exact model ID string from the provider")
    ap.add_argument("--runs", type=int, default=5, help="Runs per information level")
    ap.add_argument("--seed", type=int, default=20261028, help="Seed for the shuffled run order")
    ap.add_argument("--out", default=str(HERE / "log.jsonl"))
    ap.add_argument("--operator", default="anon")
    ap.add_argument("--max-tokens", type=int, default=16000, help="Used where the API requires it")
    ap.add_argument("--pause", type=float, default=1.0, help="Seconds between calls")
    ap.add_argument("--levels", default="L0,L1,L2", help="Comma-separated information levels. Use L0 with --runs 1 for a cheap smoke test")
    args = ap.parse_args()

    if args.provider in KEY_VARS:
        ensure_key(KEY_VARS[args.provider])

    prompts = json.loads(PROMPT_FILE.read_text())
    prompt_hash = file_sha256(PROMPT_FILE)
    commit = git_commit()
    n_items = prompts["n_items"]
    call = PROVIDERS[args.provider]
    out_path = Path(args.out)
    levels = [x.strip() for x in args.levels.split(",")]
    run_settings = {
        "runs": args.runs,
        "levels": levels,
        "seed": args.seed,
        "max_tokens": args.max_tokens,
        "pause_seconds": args.pause,
        "retries_on_invalid": 1,
        "anthropic_version": ANTHROPIC_VERSION if args.provider == "anthropic" else None,
    }
    environment = {"python": platform.python_version(), "platform": platform.platform()}

    # Resume: skip combinations that already have a stage 2 reply (not an error) for this model.
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("stage") == 2 and row.get("model_requested") == args.model and not row.get("error"):
                    done.add(row["combination_id"])

    combos = [
        (level, run)
        for level in prompts["levels"]
        if level in levels
        for run in range(1, args.runs + 1)
    ]
    random.Random(args.seed).shuffle(combos)
    print(f"{len(combos)} combinations, shuffled with seed {args.seed}. Log: {out_path}")

    def log(row):
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def run_call(messages, base):
        """One call, with one identical retry if the reply is invalid (wrong item count, cut off, or error)."""
        attempt = 0
        while True:
            attempt += 1
            started = now_utc()
            try:
                r = call(args.model, messages, args.max_tokens)
                error = None
            except SystemExit:
                raise
            except Exception as e:  # network or API error
                r = {"text": "", "model_id": None, "usage": None, "finish_reason": None,
                     "sampling": None, "request": getattr(e, "request", None),
                     "response_id": None, "request_id": None}
                error = str(e)
            items = parse_items(r["text"])
            valid = error is None and len(items) == n_items and r["finish_reason"] in FINISHED
            row = {
                **base,
                "timestamp_utc": started,
                "attempt": attempt,
                "is_retry": attempt > 1,
                "model_id_returned": r["model_id"],
                "sampling": r["sampling"],
                "request": r["request"],
                "raw_response": r["text"],
                "parsed_items": items,
                "valid": valid,
                "format_check": None if error else format_check(r["text"], n_items),
                "usage": r["usage"],
                "finish_reason": r["finish_reason"],
                "provider_response_id": r["response_id"],
                "provider_request_id": r["request_id"],
                "error": error,
            }
            log(row)
            time.sleep(args.pause)
            if valid or attempt >= 2:
                return r, items, valid

    for position, (level, run) in enumerate(combos, 1):
        cid = f"{args.model}|{level}|run{run}"
        if cid in done:
            print(f"skip {cid} (already logged)")
            continue
        common = {
            "combination_id": cid,
            "run_number": run,
            "run_order_position": position,
            "operator": args.operator,
            "provider": args.provider,
            "model_requested": args.model,
            "interface": "local" if (args.provider == "openai" and os.environ.get("OPENAI_BASE_URL")) else "api",
            "information_level": level,
            "prompt_file_hash": prompt_hash,
            "script_commit": commit,
            "protocol_version": prompts["version"],
            "run_settings": run_settings,
            "environment": environment,
        }
        stage1_prompt = f"{prompts['levels'][level]}\n\n{prompts['task']}"
        msgs = [{"role": "user", "content": stage1_prompt}]
        r1, items1, valid1 = run_call(
            msgs, {**common, "stage": 1, "context": "fresh", "prompt_text": stage1_prompt}
        )
        if not r1["text"]:
            print(f"{cid}: stage 1 returned no text, skipping stage 2 (see log)")
            continue
        msgs = msgs + [
            {"role": "assistant", "content": r1["text"]},
            {"role": "user", "content": prompts["revision"]},
        ]
        r2, items2, valid2 = run_call(
            msgs, {**common, "stage": 2, "context": "same conversation", "prompt_text": prompts["revision"]}
        )
        print(f"{cid}: stage1 valid={valid1}, stage2 valid={valid2}")


if __name__ == "__main__":
    sys.exit(main())

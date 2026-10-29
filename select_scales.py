#!/usr/bin/env python3
"""Draw AI scales for the survey at random, following PROTOCOL.md.

The pool is every valid stage 1 scale in the log, one per combination,
sorted by combination ID so the pool does not depend on the order the log
was written in. Scales are drawn uniformly at random with a recorded seed.
Nothing about item content, overlap or quality is used.

Writes <out>.csv (one row per item) and <out>.md (ready to paste into
Qualtrics), each recording the seed, pool size, models and log hash.

Response scale: every scale is fielded with the survey's response scale,
which is the `response_scale` in prompts.json (Edmondson's labels; see
DECISIONS.md, 2026-10-29). The .md file also states the scale named in the
prompt that generated each drawn scale, read from the log, and notes when
the two differ. Item wording is never changed.

Example
  python select_scales.py --log log.jsonl --n 1
"""
import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path

PROMPT_FILE = Path(__file__).resolve().parent / "prompts.json"


def generation_scale(row):
    """The response scale named in the prompt that produced this row, e.g. '7-point scale (1 = ..., 7 = ...)'."""
    m = re.search(r"\d+-point scale \([^)]*\)", row.get("prompt_text", ""))
    return m.group(0) if m else "not stated in the logged prompt"


def load_pool(log_path):
    """Valid stage 1 rows, one per combination, sorted by combination ID."""
    pool = {}
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("stage") == 1 and row.get("valid"):
            pool.setdefault(row["combination_id"], row)
    return [pool[cid] for cid in sorted(pool)]


def draw(pool, n, seed):
    return random.Random(seed).sample(pool, n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default="log.jsonl")
    ap.add_argument("--n", type=int, default=1, help="Number of scales to draw")
    ap.add_argument("--seed", type=int, default=20261028, help="Seed recorded in PROTOCOL.md")
    ap.add_argument("--out", default="selected_scales", help="Output file name without extension")
    args = ap.parse_args()

    pool = load_pool(args.log)
    if len(pool) < args.n:
        raise SystemExit(f"Only {len(pool)} valid stage 1 scales in {args.log}; cannot draw {args.n}.")
    chosen = draw(pool, args.n, args.seed)
    log_hash = hashlib.sha256(Path(args.log).read_bytes()).hexdigest()
    models = sorted({r["model_id_returned"] for r in pool})
    header = (f"seed {args.seed}; drawn {args.n} of {len(pool)} valid stage 1 scales; "
              f"models in pool: {', '.join(models)}; log sha256 {log_hash}")

    with open(f"{args.out}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scale_id", "model", "information_level", "item_number", "item_text"])
        for r in chosen:
            for i, item in enumerate(r["parsed_items"], 1):
                w.writerow([r["combination_id"], r["model_id_returned"], r["information_level"], i, item])

    survey_scale = json.loads(PROMPT_FILE.read_text())["response_scale"]
    lines = ["# Selected AI scales", "", header, "",
             f"Response scale for the survey: {survey_scale}. Use it for every scale below (decision of 2026-10-29, see DECISIONS.md).", ""]
    for k, r in enumerate(chosen, 1):
        made_for = generation_scale(r)
        lines += [f"## Scale {k}: {r['combination_id']}", ""]
        lines += [f"{i}. {item}" for i, item in enumerate(r["parsed_items"], 1)] + [""]
        lines += [f"Generated under a prompt naming: {made_for}."]
        if made_for != survey_scale:
            lines += ["This differs from the survey's response scale. The items are fielded with the survey's scale; their wording is unchanged."]
        lines += [""]
    Path(f"{args.out}.md").write_text("\n".join(lines), encoding="utf-8")

    print(header)
    for r in chosen:
        print(f"selected: {r['combination_id']}")


if __name__ == "__main__":
    main()

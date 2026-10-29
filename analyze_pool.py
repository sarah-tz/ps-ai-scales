#!/usr/bin/env python3
"""Describe the pool of AI-generated scales, following PROTOCOL.md.

Reads log.jsonl and reference/items.md. Writes:
  pool_report.csv   one row per scale (combination and stage)
  pool_summary.md   per model and stage totals, with the method and its limits

Standard library only. Nothing here changes the log or the scale draw.

Method
------
Scale used per combination and stage: the valid attempt if there is one,
otherwise the last attempt.

Negatively worded items (HEURISTIC). Text after "without", "even if" or
"even when" is ignored, since those clauses usually soften a positive item
("I can ask for help without worrying..."). The rest is checked for a
negator (not, n't, never, no one, nobody) and for negative content words
(afraid, held against, reject, worry, embarrass, ...). An item is counted
as negatively worded if it has exactly one of the two; both together are
read as a double negative ("No one ... would undermine") and count as
positive. This is a word check, not a reading of meaning. Its result on
the 10 reference items is reported in the summary.

Overlap with the validated items (LEXICAL). Items are lowercased and split
into words; common words and words every item shares by design ("this",
"team", "members") are removed. Overlap between two items is the Jaccard
index of their word sets (shared words / all distinct words). For each
scale the report gives the highest overlap of any of its items with any
reference item, and that pair. Lexical overlap misses paraphrase: an item
can carry the same idea in different words and score low.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

NEGATORS = re.compile(r"\b(not|never|no one|nobody|cannot)\b|n't\b")
NEGATIVE_WORDS = re.compile(
    r"held against|\bafraid|\breject|\bworr|\bhesitant|\bembarrass|\bpunish|put down|\bcriticiz|\bcriticis"
    r"|\bexclud|\bridicul|\bincompetent|think less|\bundermin|\bthreaten|\bdifficult|\bfear|\bpenaliz|\bpenalis"
    r"|\bdismiss|\bblame|\bfoolish"
)
SOFTENING = re.compile(r"\b(without|even if|even when)\b.*$")
STOPWORDS = set("""
a an the this that these those team teams member members people others other on in of to is are was were be
being been i i'm im my me myself you your it its and or but with for at by as from about when if would will can
could do does feel feels am have has had so than there their they them we our us who what which very often
sometimes just also
""".split())


def negatively_worded(item):
    text = SOFTENING.sub("", item.lower())
    return bool(NEGATORS.search(text)) != bool(NEGATIVE_WORDS.search(text))


def words(item):
    return {w for w in re.findall(r"[a-z']+", item.lower()) if w not in STOPWORDS}


def jaccard(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def load_reference(path):
    """Return [(label, text)] from reference/items.md, e.g. ("Edmondson 1", "...")."""
    refs, source = [], None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            source = line[3:].split()[0].rstrip(",") if not line.startswith("## Notes") else None
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if source and m:
            text = re.split(r"\s+[(\[]", m.group(2))[0].strip()
            refs.append((f"{source} {m.group(1)}", text))
    return refs


def load_scales(log_path):
    """One row per combination and stage: the valid attempt if any, else the last attempt."""
    chosen = {}
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (row["combination_id"], row["stage"])
        if key not in chosen or not chosen[key]["valid"]:
            chosen[key] = row
    return [chosen[k] for k in sorted(chosen)]


def describe(row, refs):
    items = row["parsed_items"]
    best = max(((jaccard(i, t), i, label, t) for i in items for label, t in refs), default=(0.0, "", "", ""))
    per_item = [max(jaccard(i, t) for _, t in refs) for i in items] if items else [0.0]
    return {
        "combination_id": row["combination_id"],
        "model": row["model_id_returned"] or row["model_requested"],
        "information_level": row["information_level"],
        "stage": row["stage"],
        "valid": row["valid"],
        "format_check": row.get("format_check"),
        "n_items": len(items),
        "n_negatively_worded_heuristic": sum(negatively_worded(i) for i in items),
        "max_overlap_jaccard": round(best[0], 3),
        "mean_item_best_overlap": round(sum(per_item) / len(per_item), 3),
        "best_match_reference": best[2],
        "best_match_ai_item": best[1],
        "best_match_reference_item": best[3],
    }


def summarise(report, refs, scales):
    # Known keying of the reference items, from reference/items.md (Edmondson 3 and 5 are [Inference] there).
    known_negative = {"Edmondson 1", "Edmondson 3", "Edmondson 5", "May 2", "May 3"}
    calib = [(label, negatively_worded(t), label in known_negative) for label, t in refs]
    agree = sum(h == k for _, h, k in calib)
    # Some replies mark their own reverse-scored items "(R)"; a check the word lists were not written against.
    marked = [i for s in scales for i in s["parsed_items"] if "(R)" in i]
    marked_hit = sum(negatively_worded(i) for i in marked)

    groups = defaultdict(list)
    for r in report:
        groups[(r["model"], r["stage"])].append(r)

    lines = ["# Pool summary", "",
             "Generated by `analyze_pool.py` from `log.jsonl`. Method and limits are in the script header and below.", "",
             "| Model | Stage | Scales | Valid | Scales with at least 1 negatively worded item | Mean negatively worded items per scale | Mean max overlap | Highest max overlap |",
             "|---|---|---|---|---|---|---|---|"]
    for (model, stage), rs in sorted(groups.items()):
        v = [r for r in rs if r["valid"]]
        if not v:
            lines.append(f"| {model} | {stage} | {len(rs)} | 0 | - | - | - | - |")
            continue
        neg = [r["n_negatively_worded_heuristic"] for r in v]
        ov = [r["max_overlap_jaccard"] for r in v]
        lines.append(f"| {model} | {stage} | {len(rs)} | {len(v)} | {sum(n > 0 for n in neg)} | "
                     f"{sum(neg) / len(neg):.2f} | {sum(ov) / len(ov):.2f} | {max(ov):.2f} |")

    top = sorted((r for r in report if r["valid"]), key=lambda r: -r["max_overlap_jaccard"])[:5]
    lines += ["", "## Highest overlap with a validated item", "",
              "| Scale | Stage | Overlap | AI item | Closest validated item |", "|---|---|---|---|---|"]
    lines += [f"| {r['combination_id']} | {r['stage']} | {r['max_overlap_jaccard']:.2f} | {r['best_match_ai_item']} | "
              f"{r['best_match_reference']}: {r['best_match_reference_item']} |" for r in top]
    lines += ["", "## Limits", "",
              f"- Negatively worded items are counted with a word heuristic. On the {len(refs)} validated reference items it "
              f"matches the known keying for {agree} of {len(refs)}"
              + ("." if agree == len(refs) else f" (misses: {', '.join(l for l, h, k in calib if h != k)}).")
              + " The word lists were written with these reference items in view, so this is a consistency check, not an independent test."
              " Edmondson items 3 and 5 are marked [Inference] as negatively worded in `reference/items.md`. "
              "It may still misread AI items; check flagged items by eye before relying on counts."
              + (f" Some replies marked their own reverse-scored items \"(R)\": the heuristic flags {marked_hit} of those "
                 f"{len(marked)} items. Those markers are the model's own labels, not a validated keying."
                 if marked else ""),
              "- Item text is kept as the model wrote it, including any \"(R)\" marker; remove markers before showing items to respondents.",
              "- Overlap is lexical (shared words). It misses paraphrase, so a low score does not show an item is new.",
              "- Words every item shares by design (\"this\", \"team\", \"members\") and common words are removed before comparing.",
              "- Counts describe this pool only. Model behavior is not assured to repeat across runs or over time."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default="log.jsonl")
    ap.add_argument("--reference", default="reference/items.md")
    ap.add_argument("--out", default="pool_report.csv")
    ap.add_argument("--summary", default="pool_summary.md")
    args = ap.parse_args()

    refs = load_reference(args.reference)
    scales = load_scales(args.log)
    report = [describe(r, refs) for r in scales]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0]))
        w.writeheader()
        w.writerows(report)
    summary = summarise(report, refs, scales)
    Path(args.summary).write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()

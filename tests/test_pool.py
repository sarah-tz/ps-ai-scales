import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analyze_pool import jaccard, load_reference, load_scales, negatively_worded  # noqa: E402


class NegativeWording(unittest.TestCase):
    def test_examples(self):
        self.assertTrue(negatively_worded("If I make a mistake in this team, it is held against me."))
        self.assertTrue(negatively_worded("I feel hesitant to question the way things are done in this team."))
        self.assertFalse(negatively_worded("I can ask for help in this team without worrying that others will think less of me."))
        self.assertFalse(negatively_worded("I feel comfortable proposing ideas in this team even when they might not work."))
        self.assertFalse(negatively_worded("No one in this team would deliberately act in a way that undermines my efforts."))

    def test_reference_items_load(self):
        refs = load_reference(ROOT / "reference" / "items.md")
        self.assertEqual([label for label, _ in refs][:1] + [label for label, _ in refs][-1:], ["Edmondson 1", "May 3"])
        self.assertEqual(len(refs), 10)
        self.assertEqual(refs[0][1], "If you make a mistake on this team, it is often held against you.")


class Overlap(unittest.TestCase):
    def test_identical_and_unrelated(self):
        self.assertEqual(jaccard("It is safe to take a risk on this team.", "It is safe to take a risk in this team."), 1.0)
        self.assertEqual(jaccard("It is safe to take a risk.", "Members value my skills."), 0.0)


class ScaleChoice(unittest.TestCase):
    def test_valid_attempt_is_used_over_invalid_one(self):
        rows = [
            {"combination_id": "m|L0|run1", "stage": 1, "valid": False, "parsed_items": ["a"]},
            {"combination_id": "m|L0|run1", "stage": 1, "valid": True, "parsed_items": ["b"] * 7},
            {"combination_id": "m|L0|run1", "stage": 2, "valid": True, "parsed_items": ["c"] * 7},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "test_log.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in rows))
            scales = load_scales(log)
        self.assertEqual(len(scales), 2)
        self.assertEqual(scales[0]["parsed_items"], ["b"] * 7)


if __name__ == "__main__":
    unittest.main()

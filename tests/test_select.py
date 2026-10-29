import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from select_scales import draw, load_pool  # noqa: E402


def fake_log(path):
    """Two fake models, 3 levels x 5 runs, plus one invalid stage 1 row and stage 2 rows."""
    rows = []
    for model in ("mock-a", "mock-b"):
        for level in ("L0", "L1", "L2"):
            for run in range(1, 6):
                cid = f"{model}|{level}|run{run}"
                base = {"combination_id": cid, "model_id_returned": model, "information_level": level,
                        "parsed_items": [f"{cid} item {i}" for i in range(1, 8)]}
                rows.append({**base, "stage": 2, "valid": True})
                rows.append({**base, "stage": 1, "valid": True})
    rows.append({"combination_id": "mock-a|L0|run9", "model_id_returned": "mock-a", "information_level": "L0",
                 "parsed_items": ["only one"], "stage": 1, "valid": False})
    path.write_text("\n".join(json.dumps(r) for r in rows))


class SelectScales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "test_log.jsonl"
        fake_log(self.log)

    def test_pool_is_valid_stage1_only(self):
        pool = load_pool(self.log)
        self.assertEqual(len(pool), 30)
        self.assertTrue(all(r["stage"] == 1 and r["valid"] for r in pool))

    def test_same_seed_same_draw_different_seed_different_draw(self):
        pool = load_pool(self.log)
        first = [r["combination_id"] for r in draw(pool, 1, 20261028)]
        again = [r["combination_id"] for r in draw(load_pool(self.log), 1, 20261028)]
        self.assertEqual(first, again)
        others = {draw(pool, 1, s)[0]["combination_id"] for s in range(1, 20)}
        self.assertGreater(len(others), 1)

    def test_writes_files_with_seed(self):
        out = Path(self.tmp.name) / "test_selected"
        subprocess.run([sys.executable, str(ROOT / "select_scales.py"), "--log", str(self.log), "--out", str(out)],
                       check=True, capture_output=True)
        md = out.with_suffix(".md").read_text()
        self.assertIn("seed 20261028", md)
        self.assertIn("drawn 1 of 30", md)
        self.assertEqual(len(out.with_suffix(".csv").read_text().strip().splitlines()), 8)


if __name__ == "__main__":
    unittest.main()

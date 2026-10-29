import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import generate_scales  # noqa: E402

SECRET = "sk-test-not-a-real-key"
FAKE_REPLY = {
    "id": "msg_test",
    "model": "model-x",
    "content": [{"type": "text", "text": "1. One"}],
    "usage": {"input_tokens": 1, "output_tokens": 1},
    "stop_reason": "end_turn",
}


class AnthropicRequestLogging(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SECRET})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_request_is_recorded_without_the_key(self):
        with mock.patch.object(generate_scales, "post_json", return_value=(FAKE_REPLY, {"request-id": "req_test"})) as post:
            r = generate_scales.call_anthropic("model-x", [{"role": "user", "content": "hi"}], 16000)
        # The key is sent to the API ...
        self.assertEqual(post.call_args[0][1]["x-api-key"], SECRET)
        # ... but appears nowhere in what gets logged.
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertEqual(r["request"]["body"], {"model": "model-x", "max_tokens": 16000,
                                                "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(r["request"]["headers"]["anthropic-version"], generate_scales.ANTHROPIC_VERSION)
        self.assertEqual(r["response_id"], "msg_test")
        self.assertEqual(r["request_id"], "req_test")

    def test_failed_call_keeps_request_without_the_key(self):
        with mock.patch.object(generate_scales, "post_json", side_effect=RuntimeError("HTTP 400: bad")):
            with self.assertRaises(generate_scales.CallError) as ctx:
                generate_scales.call_anthropic("model-x", [{"role": "user", "content": "hi"}], 16000)
        self.assertNotIn(SECRET, json.dumps(ctx.exception.request))
        self.assertEqual(ctx.exception.request["body"]["model"], "model-x")


class MockRunLogsSettings(unittest.TestCase):
    def test_rows_carry_run_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test_log.jsonl"
            subprocess.run(
                [sys.executable, str(ROOT / "generate_scales.py"), "--provider", "mock", "--model", "mock-1",
                 "--runs", "1", "--levels", "L0", "--pause", "0", "--out", str(out)],
                check=True, capture_output=True,
            )
            rows = [json.loads(line) for line in out.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["run_settings"]["seed"], 20261028)
            self.assertEqual(row["run_settings"]["max_tokens"], 16000)
            self.assertEqual(row["run_order_position"], 1)
            self.assertIn("python", row["environment"])
            self.assertIn("messages", row["request"]["body"])


if __name__ == "__main__":
    unittest.main()

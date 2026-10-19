import sys
import unittest
from datetime import datetime, timezone
from email.message import Message
import importlib.util
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS.parent))
from tools.gemini_retry import MAX_ATTEMPTS, retry_delay_seconds
AGENT_PATH = TOOLS / "fireworks_match_agent.py"
AGENT_SPEC = importlib.util.spec_from_file_location("fireworks_match_agent", AGENT_PATH)
match_agent = importlib.util.module_from_spec(AGENT_SPEC)
AGENT_SPEC.loader.exec_module(match_agent)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


class GeminiRetryTests(unittest.TestCase):
    def test_retry_after_delta_seconds_is_capped(self):
        self.assertEqual(retry_delay_seconds({"Retry-After": "17"}, b"", 0), 17)
        self.assertEqual(retry_delay_seconds({"Retry-After": "900"}, b"", 0), 300)

    def test_retry_after_http_date_is_parsed(self):
        now = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
        headers = {"Retry-After": "Mon, 19 Oct 2026 10:00:25 GMT"}
        self.assertEqual(retry_delay_seconds(headers, b"", 0, now=now), 25)

    def test_gemini_retry_info_body_is_parsed(self):
        body = b'{"error":{"details":[{"retryDelay":"42s"}]}}'
        self.assertEqual(retry_delay_seconds({}, body, 0), 42)

    def test_invalid_retry_after_uses_bounded_exponential_backoff(self):
        self.assertEqual(retry_delay_seconds({"Retry-After": "invalid"}, b"no json", 4), 16)
        self.assertEqual(retry_delay_seconds({}, b"", 99), 300)

    def test_retry_count_is_bounded(self):
        self.assertEqual(MAX_ATTEMPTS, 6)

    def test_match_analysis_retry_honours_retry_after_header(self):
        headers = Message()
        headers["Retry-After"] = "23"
        error = HTTPError("https://example.test", 429, "rate limited", headers, BytesIO(b"{}"))
        response = FakeResponse(
            b'{"choices":[{"message":{"content":"{\\"batch_summary\\":\\"ok\\",'
            b'\\"match_analyses\\":[{\\"match_id\\":\\"m1\\"}]}"}}],"usage":{}}'
        )
        config = {
            "api_key": "test-key",
            "model": "test-model",
            "base_url": "https://example.test/v1",
            "max_tokens": 256,
        }
        with patch.object(match_agent, "urlopen", side_effect=[error, response]) as urlopen:
            with patch.object(match_agent.time, "sleep") as sleep:
                result, _ = match_agent.call_gemini(config, [{"match_id": "m1"}], [])
        self.assertEqual(result["batch_summary"], "ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(23.0)
        error.close()


if __name__ == "__main__":
    unittest.main()

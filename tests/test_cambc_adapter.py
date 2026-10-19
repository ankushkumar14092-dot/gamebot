import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS.parent))
from tools import cambc_adapter


class CambcAdapterTests(unittest.TestCase):
    def make_adapter(self, root: Path) -> cambc_adapter.CambcAdapter:
        with patch.object(cambc_adapter.shutil, "which", return_value="cambc"):
            return cambc_adapter.CambcAdapter(root)

    def test_command_captures_metadata_and_redacts_environment_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = self.make_adapter(Path(temp))
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-secret"}):
                with patch.object(
                    cambc_adapter.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["cambc"], 0, stdout="GEMINI_API_KEY=test-secret", stderr="ok",
                    ),
                ):
                    result = adapter._run(["--version"])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "GEMINI_API_KEY=[redacted]")
            self.assertEqual(result.stderr, "ok")
            self.assertGreaterEqual(result.duration_seconds, 0)

    def test_timeout_is_returned_with_partial_output_and_no_success_code(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = self.make_adapter(Path(temp))
            timeout = subprocess.TimeoutExpired(["cambc"], 1, output=b"partial", stderr=b"detail")
            with patch.object(cambc_adapter.subprocess, "run", side_effect=timeout):
                result = adapter._run(["run", "bot-a", "bot-b"], timeout_seconds=1)
            self.assertTrue(result.timed_out)
            self.assertIsNone(result.returncode)
            self.assertEqual(result.stdout, "partial")
            self.assertEqual(result.stderr, "detail")

    def test_run_match_rejects_unsupported_seed_without_running_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = self.make_adapter(Path(temp))
            with patch.object(cambc_adapter.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "does not expose a seed"):
                    adapter.run_match("a", "b", "map.map26a", seed=123)
            run.assert_not_called()

    def test_local_match_reports_unique_statistics_and_replay_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = self.make_adapter(Path(temp))

            def write_match_artifacts(command, **_kwargs):
                output_dir = Path(command[command.index("--out-dir") + 1])
                statistics = Path(command[command.index("--statistics") + 1])
                statistics.write_text('{"match": {}}', encoding="utf-8")
                (output_dir / "test.repl26a").write_bytes(b"replay")
                return subprocess.CompletedProcess(command, 0, stdout="finished", stderr="")

            with patch.object(cambc_adapter.subprocess, "run", side_effect=write_match_artifacts):
                result = adapter.run_match("a", "b", "map.map26a")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(result.generated_artifacts), 2)
            self.assertEqual(len(set(result.generated_artifacts)), 2)

    def test_failed_build_does_not_report_a_stale_wasm_as_generated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = self.make_adapter(root)
            bot = root / "bot"
            stale_artifact = bot / ".cambc" / "build-release" / "bot.wasm"
            stale_artifact.parent.mkdir(parents=True)
            stale_artifact.write_bytes(b"previous build")
            failed = subprocess.CompletedProcess(["cambc"], 1, stdout="", stderr="compile error")
            with patch.object(cambc_adapter.subprocess, "run", return_value=failed):
                result = adapter.build_bot(bot)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.generated_artifacts, ())


if __name__ == "__main__":
    unittest.main()

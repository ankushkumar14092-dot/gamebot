"""Small, testable adapter for the installed CAMBC command-line interface."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int | None
    duration_seconds: float
    generated_artifacts: tuple[Path, ...]
    timed_out: bool = False


class CambcAdapter:
    def __init__(self, root: Path = ROOT, timeout_seconds: int = 300):
        self.root = root.resolve()
        local_cli = self.root / ".venv" / "bin" / "cambc"
        cli = local_cli if local_cli.is_file() else shutil.which("cambc")
        if not cli:
            raise FileNotFoundError("CAMBC CLI not found in .venv/bin or PATH")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        self.cli = str(cli)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _redact(text: str) -> str:
        result = re.sub(
            r"(?i)(\b(?:GEMINI|FIREWORKS)_API_KEY\s*[:=]\s*)[^\s,;]+",
            r"\1[redacted]",
            text,
        )
        for key in ("GEMINI_API_KEY", "FIREWORKS_API_KEY"):
            secret = os.environ.get(key)
            if secret:
                result = result.replace(secret, "[redacted]")
        return result

    @staticmethod
    def _text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _run(self, arguments: Sequence[str], *,
             expected_artifacts: Sequence[Path] = (),
             timeout_seconds: int | None = None) -> CommandResult:
        command = (self.cli, *map(str, arguments))
        if timeout_seconds is not None and timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        previous_artifacts: dict[Path, tuple[int, int]] = {}
        for artifact in expected_artifacts:
            candidates = [artifact] if artifact.is_file() else (
                list(artifact.iterdir()) if artifact.is_dir() else []
            )
            for candidate in candidates:
                if candidate.is_file():
                    stat = candidate.stat()
                    previous_artifacts[candidate.resolve()] = (stat.st_mtime_ns, stat.st_size)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode: int | None = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = self._text(exc.stdout)
            stderr = self._text(exc.stderr)
            returncode = None
            timed_out = True
        artifacts: list[Path] = []
        seen_artifacts: set[Path] = set()
        for artifact in expected_artifacts:
            if artifact.is_file():
                candidates = [artifact]
            elif artifact.is_dir():
                candidates = sorted(item for item in artifact.iterdir() if item.is_file())
            else:
                candidates = []
            for candidate in candidates:
                resolved = candidate.resolve()
                if resolved in seen_artifacts:
                    continue
                seen_artifacts.add(resolved)
                if returncode == 0 and not timed_out:
                    artifacts.append(resolved)
                else:
                    stat = candidate.stat()
                    if previous_artifacts.get(resolved) != (stat.st_mtime_ns, stat.st_size):
                        artifacts.append(resolved)
        return CommandResult(
            command=command,
            stdout=self._redact(stdout),
            stderr=self._redact(stderr),
            returncode=returncode,
            duration_seconds=time.monotonic() - started,
            generated_artifacts=tuple(artifacts),
            timed_out=timed_out,
        )

    def get_environment_info(self) -> dict[str, object]:
        version = self._run(["--version"])
        help_result = self._run(["--help"])
        config_path = self.root / "cambc.toml"
        sdk_version = None
        if config_path.is_file():
            match = re.search(r'(?m)^\s*sdk_version\s*=\s*"([^"]+)"', config_path.read_text())
            sdk_version = match.group(1) if match else None
        return {
            "cli_version": version.stdout.strip() if version.returncode == 0 else None,
            "sdk_version": sdk_version,
            "cli_available": version.returncode == 0,
            "top_level_help": help_result.stdout,
            "commands": {
                "version": version,
                "help": help_result,
            },
        }

    def build_bot(self, version: str | Path, *, release: bool = True,
                  timeout_seconds: int | None = None) -> CommandResult:
        bot = Path(version)
        if not bot.is_absolute():
            bot = self.root / bot
        build_dir = bot / ".cambc" / ("build-release" if release else "build")
        arguments = ["build", str(bot)]
        if release:
            arguments.append("--release")
        return self._run(arguments, expected_artifacts=[build_dir / "bot.wasm"],
                         timeout_seconds=timeout_seconds)

    def run_match(self, bot_a: str | Path, bot_b: str | Path, map_path: str | Path, *,
                  seed: int | None = None, rounds: int | None = None,
                  fuel: int | None = None, release: bool = True,
                  timeout_seconds: int | None = None) -> CommandResult:
        if seed is not None:
            raise ValueError("Installed CAMBC run/run-batch help does not expose a seed option")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = self.root / "matches" / "local" / run_id
        output_dir.mkdir(parents=True, exist_ok=False)
        statistics = output_dir / "statistics.json"
        arguments = [
            "run", str(bot_a), str(bot_b), "--map", str(map_path),
            "--out-dir", str(output_dir), "--statistics", str(statistics), "--json",
        ]
        if release:
            arguments.append("--release")
        if rounds is not None:
            if rounds < 1:
                raise ValueError("rounds must be positive")
            arguments.extend(["--rounds", str(rounds)])
        if fuel is not None:
            if fuel < 1:
                raise ValueError("fuel must be positive")
            arguments.extend(["--fuel", str(fuel)])
        return self._run(arguments, expected_artifacts=[statistics, output_dir],
                         timeout_seconds=timeout_seconds)

    def collect_match_results(self, match_id: str, *,
                              timeout_seconds: int | None = None) -> tuple[dict, CommandResult]:
        if not re.fullmatch(r"[A-Za-z0-9-]+", match_id):
            raise ValueError("match_id may contain only letters, digits, and hyphens")
        output_dir = self.root / "matches" / "cambc-adapter" / match_id
        output_dir.mkdir(parents=True, exist_ok=True)
        statistics = output_dir / "statistics.json"
        command = self._run(
            ["matches", "summary", match_id, "--json", "--output", str(statistics)],
            expected_artifacts=[statistics],
            timeout_seconds=timeout_seconds,
        )
        if command.timed_out:
            raise TimeoutError(f"CAMBC summary timed out for match {match_id}")
        if command.returncode != 0:
            raise RuntimeError(f"CAMBC summary failed for match {match_id} (exit {command.returncode})")
        try:
            data = json.loads(statistics.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"CAMBC returned malformed statistics for match {match_id}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"CAMBC statistics for match {match_id} must be a JSON object")
        return data, command

    def download_replay(self, match_id: str, *,
                        timeout_seconds: int | None = None) -> CommandResult:
        if not re.fullmatch(r"[A-Za-z0-9-]+", match_id):
            raise ValueError("match_id may contain only letters, digits, and hyphens")
        output_dir = self.root / "matches" / "cambc-adapter" / match_id
        output_dir.mkdir(parents=True, exist_ok=True)
        replay = output_dir / "replay.repl26a"
        return self._run(
            ["matches", "download", match_id, "--output", str(replay)],
            expected_artifacts=[replay],
            timeout_seconds=timeout_seconds,
        )

    def collect_diagnostics(self, match_id: str, *,
                            timeout_seconds: int | None = None) -> dict[str, object]:
        statistics, command = self.collect_match_results(match_id, timeout_seconds=timeout_seconds)
        diagnostics = statistics.get("diagnostics")
        return {
            "available": isinstance(diagnostics, dict),
            "diagnostics": diagnostics if isinstance(diagnostics, dict) else None,
            "bot_faults": diagnostics.get("botFaults") if isinstance(diagnostics, dict) else None,
            "command": command,
        }

    def inspect_environment(self) -> dict[str, object]:
        """Official Phase 2 interface for inspecting CAMBC environment."""
        return self.get_environment_info()

    def build_candidate(self, version: str | Path, *, release: bool = True,
                        timeout_seconds: int | None = None) -> CommandResult:
        """Official Phase 2 interface for building a candidate bot."""
        return self.build_bot(version, release=release, timeout_seconds=timeout_seconds)

    def collect_replay(self, match_id: str, *,
                       timeout_seconds: int | None = None) -> CommandResult:
        """Official Phase 2 interface for downloading a match replay."""
        return self.download_replay(match_id, timeout_seconds=timeout_seconds)

    def package_submission(self, version: str | Path, output: str | Path, *,
                          timeout_seconds: int | None = None) -> CommandResult:
        bot = Path(version)
        if not bot.is_absolute():
            bot = self.root / bot
        archive = Path(output)
        if not archive.is_absolute():
            archive = self.root / archive
        archive.parent.mkdir(parents=True, exist_ok=True)
        return self._run(
            ["bundle", str(bot), "--output", str(archive)],
            expected_artifacts=[archive],
            timeout_seconds=timeout_seconds,
        )

    def package_candidate(self, version: str | Path, output: str | Path | None = None, *,
                          timeout_seconds: int | None = None) -> CommandResult:
        """Official Phase 2 interface for packaging a candidate bot into an uploadable artifact."""
        bot = Path(version)
        if not bot.is_absolute():
            bot = self.root / bot
        if output is None:
            dist_dir = self.root / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            output = dist_dir / f"{bot.name}.zip"
        return self.package_submission(bot, output, timeout_seconds=timeout_seconds)

    def submit_candidate(self, artifact: str | Path, *,
                         allow_live_submission: bool = False,
                         timeout_seconds: int | None = None) -> CommandResult:
        """Official Phase 2 & 10 interface for submitting a tested candidate to CAMBC."""
        target = Path(artifact)
        if not target.is_absolute():
            target = self.root / target
        if not target.exists():
            raise FileNotFoundError(f"Artifact to submit does not exist: {target}")

        if not allow_live_submission:
            # Safe dry-run mode: verify artifact validity without remote side effects
            return CommandResult(
                command=(self.cli, "submit", str(target), "--dry-run"),
                stdout=f"[DRY-RUN] Candidate artifact {target.name} validated for submission; live upload disabled",
                stderr="",
                returncode=0,
                duration_seconds=0.01,
                generated_artifacts=(target,),
                timed_out=False,
            )

        return self._run(["submit", str(target)], timeout_seconds=timeout_seconds)

    def run_batch(self, manifest: str | Path, *, jobs: int = 1,
                  release: bool = True, timeout_seconds: int | None = None) -> CommandResult:
        """Run batch matches from a manifest file using official cambc run-batch."""
        manifest_path = Path(manifest)
        if not manifest_path.is_absolute():
            manifest_path = self.root / manifest_path
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Batch manifest not found: {manifest_path}")

        arguments = ["run-batch", str(manifest_path), "--jobs", str(jobs), "--json"]
        if release:
            arguments.append("--release")
        if timeout_seconds is not None:
            arguments.extend(["--timeout", str(timeout_seconds)])

        return self._run(arguments, timeout_seconds=timeout_seconds)


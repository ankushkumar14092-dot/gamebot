#!/usr/bin/env python3
"""Phase 8: Persistent Best-Version Registry for CAMBC bot engineering."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_FILE = Path("best_version_registry.json")


@dataclass
class VersionRecord:
    version_id: str
    git_commit: str
    artifact_checksum: str
    build_status: str  # "success", "failed", "pending"
    regression_results: dict[str, Any] = field(default_factory=dict)
    evaluation_metrics: dict[str, Any] = field(default_factory=dict)
    runtime_error_counts: int = 0
    fuel_usage: int = 0
    changes_introduced: str = ""
    promotion_decision: str = "pending"  # "promoted", "rejected", "incumbent"
    rejection_reason: str | None = None
    submission_id: str | None = None
    push_status: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BestVersionRegistry:
    def __init__(self, path: Path | str = REGISTRY_FILE):
        self.path = Path(path).resolve()
        self.data: dict[str, Any] = {
            "best_known_version": None,
            "best_known_commit": None,
            "versions": {},
            "history": [],
        }
        self.load()

    def load(self) -> None:
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @staticmethod
    def calculate_artifact_checksum(artifact_path: Path | str) -> str:
        path = Path(artifact_path)
        if not path.exists():
            return ""
        if path.is_file():
            hasher = hashlib.sha256()
            hasher.update(path.read_bytes())
            return hasher.hexdigest()
        if path.is_dir():
            hasher = hashlib.sha256()
            for file_path in sorted(path.rglob("*")):
                if file_path.is_file() and not file_path.name.startswith("."):
                    hasher.update(file_path.read_bytes())
            return hasher.hexdigest()
        return ""

    def register_candidate(self, record: VersionRecord) -> None:
        rec_dict = asdict(record)
        self.data["versions"][record.version_id] = rec_dict
        self.data["history"].append({
            "version_id": record.version_id,
            "decision": record.promotion_decision,
            "timestamp": record.timestamp,
        })
        self.save()

    def promote_version(self, version_id: str) -> None:
        if version_id in self.data["versions"]:
            rec = self.data["versions"][version_id]
            rec["promotion_decision"] = "promoted"
            self.data["best_known_version"] = version_id
            self.data["best_known_commit"] = rec.get("git_commit")
            self.save()

    def reject_version(self, version_id: str, reason: str) -> None:
        if version_id in self.data["versions"]:
            rec = self.data["versions"][version_id]
            rec["promotion_decision"] = "rejected"
            rec["rejection_reason"] = reason
            self.save()

    def get_best_known(self) -> dict[str, Any] | None:
        best_id = self.data.get("best_known_version")
        if best_id and best_id in self.data["versions"]:
            return self.data["versions"][best_id]
        return None

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        return self.data["versions"].get(version_id)

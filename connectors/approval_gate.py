"""Temporal history-gated approval verifier, single-use nonce store, and rollback snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any

from calculators import validate_safe_id


def compute_payload_sha256(payload: Any) -> str:
    """Compute canonical SHA-256 hex digest of a JSON-serializable payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_strategy_lock(brand_truth_path: pathlib.Path) -> str:
    """Return brand-truth lock status ('locked' or 'draft_pending_review' or 'missing')."""
    if not brand_truth_path.exists():
        return "missing"
    text = brand_truth_path.read_text(encoding="utf-8")
    for line in text.splitlines()[:20]:
        s = line.strip()
        if s.startswith("status:"):
            val = s.split(":", 1)[1].strip().strip('"').strip("'")
            return val
    return "draft_pending_review"


def _atomic_write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


class ApprovalGate:
    """Enforces temporal Validator -> Reviewer -> Composer approval chain and rollback snapshots."""

    def __init__(
        self,
        ledger_path: pathlib.Path,
        rollbacks_dir: pathlib.Path,
        brand_truth_path: pathlib.Path | None = None,
        ttl_minutes: int = 60,
    ) -> None:
        self.ledger_path = ledger_path
        self.rollbacks_dir = rollbacks_dir.resolve()
        self.brand_truth_path = brand_truth_path
        self.ttl_minutes = ttl_minutes
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.rollbacks_dir.mkdir(parents=True, exist_ok=True)

    def _append_event(self, event: dict[str, Any]) -> None:
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def record_validator_pass(
        self,
        subtask_id: str,
        payload: Any,
        timestamp: datetime | None = None,
    ) -> str:
        validate_safe_id(subtask_id, "subtask_id")
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        digest = compute_payload_sha256(payload)
        self._append_event(
            {
                "event_type": "validator_pass",
                "subtask_id": subtask_id,
                "payload_sha256": digest,
                "status": "pass",
                "timestamp": ts,
            }
        )
        return digest

    def record_reviewer_approval(
        self,
        subtask_id: str,
        payload: Any,
        approved: bool = True,
        timestamp: datetime | None = None,
    ) -> str:
        validate_safe_id(subtask_id, "subtask_id")
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        digest = compute_payload_sha256(payload)
        self._append_event(
            {
                "event_type": "reviewer_decision",
                "subtask_id": subtask_id,
                "payload_sha256": digest,
                "approved": bool(approved),
                "timestamp": ts,
            }
        )
        return digest

    def record_composer_signoff(
        self,
        approval_id: str,
        subtask_id: str,
        payload: Any,
        timestamp: datetime | None = None,
    ) -> str:
        validate_safe_id(approval_id, "approval_id")
        validate_safe_id(subtask_id, "subtask_id")
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        digest = compute_payload_sha256(payload)
        self._append_event(
            {
                "event_type": "composer_signoff",
                "approval_id": approval_id,
                "subtask_id": subtask_id,
                "payload_sha256": digest,
                "timestamp": ts,
            }
        )
        return digest

    def execute_write(
        self,
        action_id: str,
        subtask_id: str,
        approval_id: str,
        payload: Any,
        pre_mutation_state: dict[str, Any],
        target_file: pathlib.Path | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Verify temporal approval chain, consume single-use approval_id, snapshot rollback, and write."""
        validate_safe_id(action_id, "action_id")
        validate_safe_id(subtask_id, "subtask_id")
        validate_safe_id(approval_id, "approval_id")

        if self.brand_truth_path is not None:
            lock_status = check_strategy_lock(self.brand_truth_path)
            if lock_status != "locked":
                raise PermissionError(
                    f"Strategy-before-production lock active (brand-truth status={lock_status!r})"
                )

        current_time = now or datetime.now(timezone.utc)
        digest = compute_payload_sha256(payload)
        events = self._read_events()

        # Check single-use nonce consumption
        if any(
            e.get("event_type") == "execute_write" and e.get("approval_id") == approval_id
            for e in events
        ):
            raise PermissionError(f"Approval nonce already consumed: {approval_id}")

        # Verify Validator pass within TTL on exact payload digest
        cutoff = current_time - timedelta(minutes=self.ttl_minutes)
        validator_ok = False
        for e in reversed(events):
            if (
                e.get("event_type") == "validator_pass"
                and e.get("subtask_id") == subtask_id
                and e.get("payload_sha256") == digest
                and e.get("status") == "pass"
            ):
                ev_time = datetime.fromisoformat(e["timestamp"])
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                if ev_time >= cutoff:
                    validator_ok = True
                break
        if not validator_ok:
            raise PermissionError(
                f"No fresh Validator pass (<={self.ttl_minutes}m) matching payload sha256 {digest[:12]}"
            )

        # Verify Reviewer approval on exact payload digest
        reviewer_ok = any(
            e.get("event_type") == "reviewer_decision"
            and e.get("subtask_id") == subtask_id
            and e.get("payload_sha256") == digest
            and e.get("approved") is True
            for e in events
        )
        if not reviewer_ok:
            raise PermissionError("Missing Reviewer approved=true for exact payload hash")

        # Verify Composer sign-off matching approval_id & digest
        composer_ok = any(
            e.get("event_type") == "composer_signoff"
            and e.get("approval_id") == approval_id
            and e.get("subtask_id") == subtask_id
            and e.get("payload_sha256") == digest
            for e in events
        )
        if not composer_ok:
            raise PermissionError(f"Missing Composer signoff for approval_id={approval_id}")

        # Write pre-mutation rollback snapshot
        snap_path = (self.rollbacks_dir / f"{action_id}.json").resolve()
        if not snap_path.is_relative_to(self.rollbacks_dir):
            raise ValueError("Rollback snapshot path escapes rollbacks_dir")

        snapshot = {
            "action_id": action_id,
            "subtask_id": subtask_id,
            "approval_id": approval_id,
            "payload_sha256": digest,
            "target_file": str(target_file) if target_file else None,
            "pre_mutation_state": pre_mutation_state,
            "captured_at": current_time.isoformat(),
        }
        _atomic_write_json(snap_path, snapshot)

        if target_file is not None:
            _atomic_write_json(target_file, payload)

        self._append_event(
            {
                "event_type": "execute_write",
                "action_id": action_id,
                "subtask_id": subtask_id,
                "approval_id": approval_id,
                "payload_sha256": digest,
                "rollback_snapshot": str(snap_path),
                "timestamp": current_time.isoformat(),
            }
        )
        return {"status": "executed", "action_id": action_id, "rollback_snapshot": str(snap_path)}

    def rollback(self, action_id: str) -> dict[str, Any]:
        """Restore pre-mutation state from data/rollbacks/<action_id>.json."""
        validate_safe_id(action_id, "action_id")
        snap_path = (self.rollbacks_dir / f"{action_id}.json").resolve()
        if not snap_path.is_relative_to(self.rollbacks_dir) or not snap_path.exists():
            raise FileNotFoundError(f"Rollback snapshot not found: {action_id}")
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        target = snapshot.get("target_file")
        pre_state = snapshot["pre_mutation_state"]
        if target:
            _atomic_write_json(pathlib.Path(target), pre_state)
        self._append_event(
            {
                "event_type": "rollback_executed",
                "action_id": action_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"status": "rolled_back", "action_id": action_id, "restored_state": pre_state}

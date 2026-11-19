"""Lightweight SQLite cohort identity resolver (CDP.com AI CMO Customer Intelligence Loop)."""

from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import os
import pathlib
import sqlite3
from typing import Any

from calculators import to_float


def anonymize_customer_key(raw_email_or_id: str, salt: str | None = None) -> str:
    """Hash customer identifier with SHA-256 (or HMAC-SHA256 when FREECMO_PII_SALT is set) so raw PII is never stored."""
    normalized = (raw_email_or_id or "").strip().lower()
    if not normalized:
        raise ValueError("Customer identifier cannot be empty")
    effective_salt = salt if salt is not None else os.environ.get("FREECMO_PII_SALT", "")
    if effective_salt:
        return hmac.new(effective_salt.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


class IdentityResolver:
    """Joins first-touch acquisition UTM, CRM/email segment, and repeat-order LTV in SQLite."""

    def __init__(self, db_path: pathlib.Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cohort_profiles (
                    anon_customer_id TEXT PRIMARY KEY,
                    first_touch_utm TEXT NOT NULL DEFAULT 'unknown',
                    acquisition_channel TEXT NOT NULL DEFAULT 'unknown',
                    crm_segment TEXT NOT NULL DEFAULT 'unassigned',
                    orders_count INTEGER NOT NULL DEFAULT 0,
                    ltv_usd REAL NOT NULL DEFAULT 0.0,
                    acquisition_cost_usd REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cohort_segment ON cohort_profiles(crm_segment);"
            )

    def upsert_customer_record(
        self,
        raw_identifier: str,
        first_touch_utm: str | None = None,
        acquisition_channel: str | None = None,
        crm_segment: str | None = None,
        orders_count: int | None = None,
        ltv_usd: float | None = None,
        acquisition_cost_usd: float | None = None,
    ) -> str:
        anon_id = anonymize_customer_key(raw_identifier)
        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                "SELECT * FROM cohort_profiles WHERE anon_customer_id = ?", (anon_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO cohort_profiles (
                        anon_customer_id, first_touch_utm, acquisition_channel,
                        crm_segment, orders_count, ltv_usd, acquisition_cost_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        anon_id,
                        first_touch_utm or "unknown",
                        acquisition_channel or "unknown",
                        crm_segment or "unassigned",
                        int(orders_count or 0),
                        float(ltv_usd or 0.0),
                        float(acquisition_cost_usd or 0.0),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE cohort_profiles SET
                        first_touch_utm = COALESCE(?, first_touch_utm),
                        acquisition_channel = COALESCE(?, acquisition_channel),
                        crm_segment = COALESCE(?, crm_segment),
                        orders_count = COALESCE(?, orders_count),
                        ltv_usd = COALESCE(?, ltv_usd),
                        acquisition_cost_usd = COALESCE(?, acquisition_cost_usd),
                        updated_at = datetime('now')
                    WHERE anon_customer_id = ?
                    """,
                    (
                        first_touch_utm,
                        acquisition_channel,
                        crm_segment,
                        orders_count,
                        ltv_usd,
                        acquisition_cost_usd,
                        anon_id,
                    ),
                )
        return anon_id

    def unify_csv_records(self, rows: list[dict[str, Any]], source_kind: str) -> int:
        """Ingest normalized CSV rows from acquisition, CRM, or orders into unified cohorts."""
        updated = 0
        for row in rows:
            raw_id = row.get("email") or row.get("customer_id") or row.get("anon_customer_id")
            if not raw_id or str(raw_id).lower() == "unknown":
                continue
            orders = to_float(row.get("orders_count"))
            ltv = to_float(row.get("ltv_usd"))
            if ltv is None:
                ltv = to_float(row.get("revenue_usd"))
            cac = to_float(row.get("acquisition_cost_usd"))
            if cac is None:
                cac = to_float(row.get("spend_usd"))
            self.upsert_customer_record(
                raw_identifier=str(raw_id),
                first_touch_utm=str(row["first_touch_utm"]) if row.get("first_touch_utm") else None,
                acquisition_channel=str(row["acquisition_channel"]) if row.get("acquisition_channel") else (source_kind if source_kind in ("paid_search", "paid_social", "organic") else None),
                crm_segment=str(row["crm_segment"]) if row.get("crm_segment") else None,
                orders_count=int(orders) if orders is not None else None,
                ltv_usd=ltv,
                acquisition_cost_usd=cac,
            )
            updated += 1
        return updated

    def summarize_segments(self) -> list[dict[str, Any]]:
        """Aggregate unified cohort LTV, repeat rate, and acquisition cost by CRM segment."""
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT
                    crm_segment,
                    COUNT(*) AS customers,
                    SUM(orders_count) AS total_orders,
                    ROUND(AVG(ltv_usd), 2) AS avg_ltv_usd,
                    ROUND(SUM(ltv_usd), 2) AS total_ltv_usd,
                    ROUND(SUM(acquisition_cost_usd), 2) AS total_acq_cost_usd,
                    ROUND(100.0 * SUM(CASE WHEN orders_count >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct
                FROM cohort_profiles
                GROUP BY crm_segment
                ORDER BY total_ltv_usd DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

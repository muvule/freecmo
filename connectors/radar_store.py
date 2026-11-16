"""Local SQLite FTS5 Market Radar & Pain-Cluster Graph (Lling0000/OpenCMO + opencmo.ai pattern)."""

from __future__ import annotations

import pathlib
import re
import sqlite3
from typing import Any


def _escape_fts5_query(query: str) -> str:
    """Tokenize and double-quote terms to prevent FTS5 syntax injection errors."""
    tokens = re.findall(r"[A-Za-z0-9_]+", query or "")
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


class RadarStore:
    """SQLite FTS5 store linking competitors, keywords, community threads, and pain clusters."""

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
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS competitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    positioning TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term TEXT NOT NULL UNIQUE,
                    intent TEXT DEFAULT 'commercial',
                    organic_rank REAL,
                    geo_citation_score REAL
                );
                CREATE TABLE IF NOT EXISTS pain_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    mention_count INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS community_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    body_excerpt TEXT NOT NULL,
                    pain_cluster_id INTEGER REFERENCES pain_clusters(id),
                    competitor_id INTEGER REFERENCES competitors(id),
                    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS threads_fts USING fts5(
                    title,
                    body_excerpt,
                    platform,
                    content='community_threads',
                    content_rowid='id'
                );
                CREATE TRIGGER IF NOT EXISTS threads_ai AFTER INSERT ON community_threads BEGIN
                    INSERT INTO threads_fts(rowid, title, body_excerpt, platform)
                    VALUES (new.id, new.title, new.body_excerpt, new.platform);
                END;
                CREATE TRIGGER IF NOT EXISTS threads_ad AFTER DELETE ON community_threads BEGIN
                    INSERT INTO threads_fts(threads_fts, rowid, title, body_excerpt, platform)
                    VALUES ('delete', old.id, old.title, old.body_excerpt, old.platform);
                END;
                CREATE TRIGGER IF NOT EXISTS threads_au AFTER UPDATE ON community_threads BEGIN
                    INSERT INTO threads_fts(threads_fts, rowid, title, body_excerpt, platform)
                    VALUES ('delete', old.id, old.title, old.body_excerpt, old.platform);
                    INSERT INTO threads_fts(rowid, title, body_excerpt, platform)
                    VALUES (new.id, new.title, new.body_excerpt, new.platform);
                END;
                """
            )

    def upsert_competitor(self, name: str, domain: str, positioning: str = "") -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO competitors(name, domain, positioning)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET domain=excluded.domain, positioning=excluded.positioning
                """,
                (name, domain, positioning),
            )
            row = conn.execute("SELECT id FROM competitors WHERE name = ?", (name,)).fetchone()
            return int(row["id"])

    def upsert_keyword(
        self,
        term: str,
        intent: str = "commercial",
        organic_rank: float | None = None,
        geo_citation_score: float | None = None,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO keywords(term, intent, organic_rank, geo_citation_score)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(term) DO UPDATE SET
                    intent=excluded.intent,
                    organic_rank=COALESCE(excluded.organic_rank, keywords.organic_rank),
                    geo_citation_score=COALESCE(excluded.geo_citation_score, keywords.geo_citation_score)
                """,
                (term, intent, organic_rank, geo_citation_score),
            )
            row = conn.execute("SELECT id FROM keywords WHERE term = ?", (term,)).fetchone()
            return int(row["id"])

    def upsert_pain_cluster(self, cluster_name: str, summary: str, increment: int = 1) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pain_clusters(cluster_name, summary, mention_count)
                VALUES (?, ?, ?)
                ON CONFLICT(cluster_name) DO UPDATE SET
                    summary=excluded.summary,
                    mention_count=pain_clusters.mention_count + excluded.mention_count
                """,
                (cluster_name, summary, increment),
            )
            row = conn.execute("SELECT id FROM pain_clusters WHERE cluster_name = ?", (cluster_name,)).fetchone()
            return int(row["id"])

    def add_community_thread(
        self,
        platform: str,
        url: str,
        title: str,
        body_excerpt: str,
        pain_cluster_name: str | None = None,
        competitor_name: str | None = None,
    ) -> int:
        cluster_id = self.upsert_pain_cluster(pain_cluster_name, title) if pain_cluster_name else None
        comp_id = None
        if competitor_name:
            with self._connect() as conn:
                r = conn.execute("SELECT id FROM competitors WHERE name = ?", (competitor_name,)).fetchone()
                if r:
                    comp_id = int(r["id"])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO community_threads(platform, url, title, body_excerpt, pain_cluster_id, competitor_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    body_excerpt=excluded.body_excerpt,
                    pain_cluster_id=COALESCE(excluded.pain_cluster_id, community_threads.pain_cluster_id)
                """,
                (platform, url, title, body_excerpt, cluster_id, comp_id),
            )
            row = conn.execute("SELECT id FROM community_threads WHERE url = ?", (url,)).fetchone()
            return int(row["id"])

    def search_threads(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        fts_query = _escape_fts5_query(query)
        if fts_query == '""':
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ct.id, ct.platform, ct.url, ct.title, ct.body_excerpt, pc.cluster_name
                FROM threads_fts
                JOIN community_threads ct ON ct.id = threads_fts.rowid
                LEFT JOIN pain_clusters pc ON pc.id = ct.pain_cluster_id
                WHERE threads_fts MATCH ?
                ORDER BY bm25(threads_fts)
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def top_pain_clusters(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, cluster_name, summary, mention_count FROM pain_clusters ORDER BY mention_count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def draft_community_reply(reply_body: str, brand_name: str) -> str:
    """Append mandatory FTC/community affiliation disclosure if not already present."""
    disclosure = f"(Disclosure: I built/work on {brand_name})"
    text = (reply_body or "").strip()
    if disclosure.lower() in text.lower():
        return text
    return f"{text}\n\n{disclosure}"

"""Local bibliography database backed by SQLite with FTS5 search.

Stores bibliographic records for local reference matching.
Replaces the in-memory JSON PublicAdminAcademicDB with persistent storage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = ROOT_DIR / "backend" / "data" / "bibliography" / "bibliography.db"


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    t = title.lower().strip()
    t = re.sub(r"[\[\]【】（）\(\)《》，。；：、！？""''\"\']", "", t)
    t = re.sub(r"\s+", " ", t)
    t = t.replace("（", "").replace("）", "").replace("［", "").replace("］", "")
    t = re.sub(r"\[j\]|\[m\]|\[d\]|\[c\]|\[n\]|\[eb/ol\]|\[eb/ol\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"doi:?\s*10\.\d{4,}[^\s]*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"https?://[^\s]+", "", t)
    return t.strip()


class BibliographyDB:
    """SQLite-based bibliography database with FTS5 text search."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS works (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL DEFAULT '',
                authors_json TEXT DEFAULT '[]',
                first_author TEXT DEFAULT '',
                year INTEGER,
                journal TEXT DEFAULT '',
                publisher TEXT DEFAULT '',
                volume TEXT DEFAULT '',
                issue TEXT DEFAULT '',
                pages TEXT DEFAULT '',
                doi TEXT DEFAULT '',
                isbn TEXT DEFAULT '',
                url TEXT DEFAULT '',
                abstract TEXT DEFAULT '',
                keywords_json TEXT DEFAULT '[]',
                source_platform TEXT DEFAULT 'manual_import',
                language TEXT DEFAULT 'zh',
                ref_type TEXT DEFAULT 'J',
                raw_reference TEXT DEFAULT '',
                metadata_quality_score REAL DEFAULT 0.0,
                imported_at TEXT DEFAULT '',
                import_batch_id TEXT DEFAULT '',
                fingerprint TEXT DEFAULT ''
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS import_batches (
                id TEXT PRIMARY KEY,
                filename TEXT DEFAULT '',
                format TEXT DEFAULT '',
                record_count INTEGER DEFAULT 0,
                imported_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                imported_at TEXT DEFAULT ''
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
                title, journal, first_author, abstract,
                content='works', content_rowid='rowid'
            )
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS works_ai AFTER INSERT ON works BEGIN
                INSERT INTO works_fts(rowid, title, journal, first_author, abstract)
                VALUES (new.rowid, new.title, new.journal, new.first_author, new.abstract);
            END;
        """)
        self._conn.commit()

    def insert(self, record: Dict[str, Any], batch_id: str = "") -> Optional[str]:
        ref_id = record.get("id") or hashlib.md5(
            json.dumps(record.get("title", ""), sort_keys=True).encode()
        ).hexdigest()[:16]
        norm_title = _normalize_title(record.get("title", ""))
        fingerprint = hashlib.md5(norm_title.encode()).hexdigest()

        existing = self._conn.execute(
            "SELECT id FROM works WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if existing:
            return None

        authors = record.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(";") if a.strip()]
        first_author = authors[0] if authors else ""

        keywords = record.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(";") if k.strip()]

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO works (id, title, normalized_title, authors_json, first_author,
                year, journal, publisher, volume, issue, pages, doi, isbn, url, abstract,
                keywords_json, source_platform, language, ref_type, raw_reference,
                metadata_quality_score, imported_at, import_batch_id, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ref_id, record.get("title", ""), norm_title, json.dumps(authors, ensure_ascii=False),
            first_author, record.get("year"), record.get("journal", ""),
            record.get("publisher", ""), record.get("volume", ""), record.get("issue", ""),
            record.get("pages", ""), record.get("doi", ""), record.get("isbn", ""),
            record.get("url", ""), record.get("abstract", ""),
            json.dumps(keywords, ensure_ascii=False),
            record.get("source_platform", "manual_import"), record.get("language", "zh"),
            record.get("ref_type", "J"), record.get("raw_reference", ""),
            record.get("metadata_quality_score", 0.0), now, batch_id, fingerprint,
        ))
        self._conn.commit()
        return ref_id

    def bulk_import(self, records: List[Dict[str, Any]], filename: str = "", format: str = "json") -> Dict[str, int]:
        batch_id = hashlib.md5(f"{filename}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
        imported = 0
        duplicates = 0
        errors = 0
        for rec in records:
            try:
                ref_id = self.insert(rec, batch_id)
                if ref_id:
                    imported += 1
                else:
                    duplicates += 1
            except Exception as e:
                LOGGER.warning("Import error for record %s: %s", rec.get("title", "?")[:50], e)
                errors += 1

        self._conn.execute("""
            INSERT INTO import_batches (id, filename, format, record_count, imported_count, duplicate_count, error_count, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, filename, format, len(records), imported, duplicates, errors,
              datetime.now(timezone.utc).isoformat()))
        self._conn.commit()
        return {"imported": imported, "duplicates": duplicates, "errors": errors, "batch_id": batch_id}

    def search(self, title: str = "", author: str = "", year: Optional[int] = None, journal: str = "", top_k: int = 10) -> List[Dict[str, Any]]:
        conditions = []
        params: List[Any] = []
        if title:
            conditions.append("works_fts MATCH ?")
            params.append(title)
        if author:
            conditions.append("first_author LIKE ?")
            params.append(f"%{author}%")
        if year is not None:
            conditions.append("year = ?")
            params.append(year)
        if journal:
            conditions.append("journal LIKE ?")
            params.append(f"%{journal}%")

        if conditions and title:
            query = f"""
                SELECT w.* FROM works w
                JOIN works_fts ON w.rowid = works_fts.rowid
                WHERE {' AND '.join(conditions)}
                ORDER BY rank
                LIMIT ?
            """
            params.append(top_k)
        elif conditions:
            query = f"""
                SELECT * FROM works
                WHERE {' AND '.join(conditions)}
                ORDER BY year DESC
                LIMIT ?
            """
            params.append(top_k)
        else:
            query = "SELECT * FROM works ORDER BY imported_at DESC LIMIT ?"
            params.append(top_k)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_by_fuzzy_title(self, title: str, top_k: int = 5) -> List[Dict[str, Any]]:
        norm = _normalize_title(title)
        from difflib import SequenceMatcher
        all_rows = self._conn.execute("SELECT * FROM works ORDER BY year DESC LIMIT 200").fetchall()
        results = []
        for row in all_rows:
            d = self._row_to_dict(row)
            sim = SequenceMatcher(None, norm, d.get("normalized_title", "")).ratio()
            if sim >= 0.4:
                d["match_score"] = round(sim, 3)
                results.append(d)
        results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return results[:top_k]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for key in ("authors_json", "keywords_json"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key.replace("_json", "s")] = json.loads(d[key])
                except json.JSONDecodeError:
                    d[key.replace("_json", "s")] = []
        return d

    def stats(self) -> Dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        zh = self._conn.execute("SELECT COUNT(*) FROM works WHERE language='zh'").fetchone()[0]
        en = self._conn.execute("SELECT COUNT(*) FROM works WHERE language='en'").fetchone()[0]
        by_type = {r[0]: r[1] for r in self._conn.execute("SELECT ref_type, COUNT(*) FROM works GROUP BY ref_type").fetchall()}
        return {"total_works": total, "zh_count": zh, "en_count": en, "by_type": by_type}

    def get_import_batches(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM import_batches ORDER BY imported_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()


_bibliography_db: Optional[BibliographyDB] = None


def get_bibliography_db() -> BibliographyDB:
    global _bibliography_db
    if _bibliography_db is None:
        _bibliography_db = BibliographyDB()
    return _bibliography_db

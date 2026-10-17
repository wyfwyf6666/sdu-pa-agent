"""Local authoritative bibliography database.

Stores user-imported bibliographic records from CNKI, WoS, Scopus, etc.
Used as a supplementary matching layer alongside open providers.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[4]
DATA_DIR = (Path(os.getenv("LOCAL_BIBLIOGRAPHY_DATA_DIR", "")) if os.getenv("LOCAL_BIBLIOGRAPHY_DATA_DIR") else BASE_DIR / "backend" / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("LOCAL_BIBLIOGRAPHY_DB", str(DATA_DIR / "local_bibliography.sqlite3"))).resolve()

LOGGER.info("[LocalBibliography] DB_PATH=%s", DB_PATH)

try:
    from openpyxl import load_workbook
except Exception:
    load_workbook = None


@dataclass
class BibRecord:
    id: str = ""
    import_batch_id: str = ""
    source_name: str = ""
    title: str = ""
    normalized_title: str = ""
    authors: str = ""
    normalized_authors: str = ""
    year: str = ""
    journal: str = ""
    publisher: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    document_type: str = "J"
    raw_reference: str = ""
    imported_at: int = 0


@dataclass
class ImportBatch:
    id: str = ""
    file_name: str = ""
    file_type: str = ""
    source_name: str = ""
    institution_source: str = ""
    total_count: int = 0
    success_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0
    created_at: int = 0
    status: str = ""
    error_summary: str = ""


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    if not s: return ""
    s = str(s).replace("　", " ").strip()
    return re.sub(r"\s+", " ", s)


def _norm_title(t: str) -> str:
    t = _clean(t).lower()
    t = re.sub(r"\[[a-z/]+\]", "", t, flags=re.I)
    t = re.sub(r"(doi\s*:.*)$", "", t, flags=re.I)
    t = re.sub(r"https?://\S+", "", t, flags=re.I)
    t = re.sub(r"[《》“\"'‘’\[\]【】(){}<>:：,，.。;；!！?？\-—_·/\s]", "", t)
    return t.strip()


def _norm_authors(a: str) -> str:
    a = _clean(a).lower()
    for w in ["等", "et al.", "et al", "主编", "编著", "著"]:
        a = a.replace(w, "")
    return re.sub(r"[，,、;；\s\.·\-]", "", a).strip()


def _norm_doi(d: str) -> str:
    d = _clean(d).lower()
    for p in ["doi:", "https://doi.org/", "http://doi.org/"]:
        d = d.replace(p, "")
    return d.rstrip(".")


def _sim(a: str, b: str) -> float:
    a, b = a or "", b or ""
    if not a or not b: return 0.0
    return SequenceMatcher(None, a, b).ratio()


HEADER_ALIASES = {
    "title": ["title", "题名", "篇名", "文献题名"],
    "authors": ["authors", "author", "作者", "责任者"],
    "year": ["year", "年份", "发表年份", "出版年"],
    "journal": ["journal", "source", "期刊", "刊名", "来源", "来源出版物"],
    "publisher": ["publisher", "出版社", "出版者"],
    "doi": ["doi", "DOI"],
    "document_type": ["document_type", "type", "文献类型"],
    "raw_reference": ["raw_reference", "reference", "引文", "参考文献", "标准引文", "原始题录"],
}


def _normalize_header(h: str) -> str:
    h = _clean(h).lower()
    for std, aliases in HEADER_ALIASES.items():
        if h in [a.lower() for a in aliases]:
            return std
    return h


# ---------------------------------------------------------------------------
# SQLite Store
# ---------------------------------------------------------------------------

class BibStore:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS bibliographic_records (
                id TEXT PRIMARY KEY, import_batch_id TEXT, source_name TEXT,
                title TEXT, normalized_title TEXT, authors TEXT, normalized_authors TEXT,
                year TEXT, journal TEXT, publisher TEXT, volume TEXT, issue TEXT,
                pages TEXT, doi TEXT, url TEXT, document_type TEXT,
                raw_reference TEXT, imported_at INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS import_batches (
                id TEXT PRIMARY KEY, file_name TEXT, file_type TEXT,
                source_name TEXT, institution_source TEXT,
                total_count INTEGER, success_count INTEGER,
                duplicate_count INTEGER, failed_count INTEGER,
                created_at INTEGER, status TEXT, error_summary TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lb_title ON bibliographic_records(normalized_title)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lb_doi ON bibliographic_records(doi)")
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM bibliographic_records").fetchone()[0]

    def search(self, q: str = "", limit: int = 50) -> List[Dict]:
        q = _clean(q)
        with self._connect() as conn:
            if not q:
                rows = conn.execute("SELECT * FROM bibliographic_records ORDER BY imported_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                like = f"%{q}%"
                rows = conn.execute("""SELECT * FROM bibliographic_records
                    WHERE title LIKE ? OR authors LIKE ? OR journal LIKE ? OR year LIKE ? OR doi LIKE ?
                    ORDER BY imported_at DESC LIMIT ?""",
                    (like, like, like, like, like, limit)).fetchall()
            return [dict(r) for r in rows]

    def list_batches(self) -> List[Dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM import_batches ORDER BY created_at DESC").fetchall()]

    def delete_batch(self, batch_id: str):
        with self._connect() as conn:
            c = conn.execute("SELECT COUNT(*) FROM bibliographic_records WHERE import_batch_id=?", (batch_id,)).fetchone()[0]
            conn.execute("DELETE FROM bibliographic_records WHERE import_batch_id=?", (batch_id,))
            conn.execute("DELETE FROM import_batches WHERE id=?", (batch_id,))
            conn.commit()
            return {"deleted_records": c}

    def import_transaction(self, records: List[BibRecord], batch: ImportBatch) -> Dict:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            ok, dup, fail = 0, 0, 0
            for r in records:
                try:
                    if conn.execute("SELECT id FROM bibliographic_records WHERE id=?", (r.id,)).fetchone():
                        dup += 1
                    else:
                        data = asdict(r)
                        flds = list(data.keys())
                        conn.execute(f"INSERT INTO bibliographic_records ({','.join(flds)}) VALUES ({','.join(['?']*len(flds))})", [data[f] for f in flds])
                        ok += 1
                except Exception as e:
                    fail += 1
            conn.execute("""INSERT INTO import_batches (id,file_name,file_type,source_name,institution_source,total_count,success_count,duplicate_count,failed_count,created_at,status,error_summary)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (batch.id, batch.file_name, batch.file_type, batch.source_name, batch.institution_source, len(records), ok, dup, fail, batch.created_at, "success" if fail == 0 else "partial", ""))
            conn.commit()
            return {"total_count": len(records), "success_count": ok, "duplicate_count": dup, "failed_count": fail}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

def match_reference(ref: Dict[str, Any]) -> Dict[str, Any]:
    """Match a parsed reference against the local bibliography. Returns status/scores only."""
    store = BibStore()
    title = _clean(ref.get("title", ""))
    authors = _clean(ref.get("authors", ""))
    year = str(ref.get("year", ""))
    doi = _norm_doi(ref.get("doi", ""))
    journal = _clean(ref.get("journal", ""))

    if isinstance(authors, list):
        authors = "; ".join(authors)

    n_title = _norm_title(title)
    n_authors = _norm_authors(authors)
    n_journal = _norm_title(journal)

    # DOI exact match
    if doi:
        with store._connect() as conn:
            row = conn.execute("SELECT * FROM bibliographic_records WHERE doi=?", (doi,)).fetchone()
            if row:
                return {"local_match_status": "verified_by_local_library", "local_match_score": 1.0, "local_matched_record": dict(row), "local_match_reasons": ["DOI exact match"]}

    # Title + author + year search
    candidates = []
    with store._connect() as conn:
        if n_title:
            rows = conn.execute("""SELECT * FROM bibliographic_records
                WHERE normalized_title LIKE ? OR normalized_authors LIKE ? OR year=?
                LIMIT 30""", (f"%{n_title[:30]}%", f"%{n_authors[:10]}%" if n_authors else "%", year)).fetchall()
            candidates = [dict(r) for r in rows]

    best_score, best_record = 0.0, None
    for c in candidates:
        ts = _sim(n_title, c.get("normalized_title", ""))
        a_s = _sim(n_authors, c.get("normalized_authors", ""))
        y_s = 1.0 if year and c.get("year") and year == str(c.get("year")) else 0.0
        j_s = _sim(n_journal, _norm_title(c.get("journal", "")))
        score = ts * 0.50 + a_s * 0.25 + y_s * 0.15 + j_s * 0.10

        if score > best_score:
            best_score = score
            best_record = c

    if best_score >= 0.88:
        return {"local_match_status": "verified_by_local_library", "local_match_score": round(best_score, 4), "local_matched_record": best_record, "local_match_reasons": ["High confidence match"]}
    elif best_score >= 0.70:
        return {"local_match_status": "likely_real_by_local_library", "local_match_score": round(best_score, 4), "local_matched_record": best_record, "local_match_reasons": ["Partial match"]}
    return {"local_match_status": "not_matched", "local_match_score": round(best_score, 4) if best_score else 0.0}


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------

def _record_from_row(row: Dict[str, Any], batch_id: str, source_name: str) -> BibRecord:
    nr = {}
    for k, v in row.items():
        nr[_normalize_header(str(k))] = "" if v is None else str(v).strip()
    title = _clean(nr.get("title", ""))
    authors = _clean(nr.get("authors", ""))
    year = str(nr.get("year", "")).strip()
    if year.endswith(".0"): year = year[:-2]
    journal = _clean(nr.get("journal", ""))
    publisher = _clean(nr.get("publisher", ""))
    doi = _norm_doi(nr.get("doi", ""))
    doc_type = _clean(nr.get("document_type", "J")) or "J"
    raw_ref = _clean(nr.get("raw_reference", ""))
    if not raw_ref:
        raw_ref = f"{authors}. {title}[{doc_type}]. {journal or publisher}, {year}."
    rid = hashlib.md5(f"{doi}|{_norm_title(title)}|{_norm_authors(authors)}|{year}".encode()).hexdigest()
    return BibRecord(id=rid, import_batch_id=batch_id, source_name=source_name, title=title,
        normalized_title=_norm_title(title), authors=authors, normalized_authors=_norm_authors(authors),
        year=year, journal=journal, publisher=publisher, doi=doi, document_type=doc_type.upper(),
        raw_reference=raw_ref, imported_at=int(time.time()))


def import_file(file_path: Path, source_name: str = "CNKI", institution_source: str = "") -> Dict:
    suffix = file_path.suffix.lower()
    batch_id = hashlib.md5(f"{file_path.name}{time.time()}".encode()).hexdigest()[:12]
    records = []

    if suffix == ".txt":
        text = file_path.read_text(encoding="utf-8-sig", errors="ignore")
        for part in re.split(r"(?=\[\d+\])", text):
            part = part.strip()
            if re.match(r"\[\d+\]", part):
                parsed = _parse_gbt7714(part, batch_id, source_name)
                if parsed.title: records.append(parsed)
    elif suffix == ".csv":
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                r = _record_from_row(row, batch_id, source_name)
                if r.title or r.raw_reference: records.append(r)
    elif suffix in (".xlsx", ".xls"):
        if not load_workbook: raise RuntimeError("需要 openpyxl: pip install openpyxl")
        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        try:
            rows = list(wb.active.iter_rows(values_only=True))
            if rows:
                headers = [_clean(str(x or "")) for x in rows[0]]
                for vals in rows[1:]:
                    row = {}
                    for i, v in enumerate(vals):
                        if i < len(headers) and headers[i]:
                            row[_normalize_header(headers[i])] = "" if v is None else str(v).strip()
                    if row.get("title") or row.get("raw_reference"):
                        records.append(_record_from_row(row, batch_id, source_name))
        finally:
            wb.close()
    elif suffix == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
        items = data if isinstance(data, list) else data.get("records", [])
        for it in items:
            r = _record_from_row(it, batch_id, source_name)
            if r.title or r.raw_reference: records.append(r)

    batch = ImportBatch(id=batch_id, file_name=file_path.name, file_type=suffix.replace(".", ""),
        source_name=source_name, institution_source=institution_source,
        created_at=int(time.time()))
    store = BibStore()
    result = store.import_transaction(records, batch)
    return {"import_batch_id": batch_id, "file_name": file_path.name, "file_type": suffix.replace(".", ""),
        "source_name": source_name, "institution_source": institution_source,
        **result, "local_total_records": store.count()}


def _parse_gbt7714(raw: str, batch_id: str, source_name: str) -> BibRecord:
    raw = _clean(raw)
    raw_no_idx = re.sub(r"^\[\d+\]\s*", "", raw).strip()
    doi = _norm_doi(re.search(r"10\.\d{4,}/[^\s。,;]+", raw_no_idx).group(0) if re.search(r"10\.\d{4,}/[^\s。,;]+", raw_no_idx) else "")
    doc_type = "J"
    m = re.search(r"\[([A-Z]+(?:/[A-Z]+)?)\]", raw_no_idx, re.I)
    if m: doc_type = m.group(1).upper()
    authors, title, journal, year = "", "", "", ""
    main = re.match(r"^(.+?)\.(.+?)\[([A-Z]+(?:/[A-Z]+)?)\]\.(.+)$", raw_no_idx, re.I)
    if main:
        authors = _clean(main.group(1))
        title = _clean(main.group(2))
        doc_type = main.group(3).upper()
        rest = _clean(main.group(4))
        ym = re.search(r"(19\d{2}|20\d{2})", rest)
        if ym: year = ym.group(1)
        if doc_type == "J" and year:
            journal = _clean(rest.split(year)[0].rstrip(",，.。 "))
    else:
        ym = re.search(r"(19\d{2}|20\d{2})", raw_no_idx)
        if ym: year = ym.group(1)
        parts = raw_no_idx.split(".")
        if len(parts) >= 2: authors, title = _clean(parts[0]), _clean(parts[1])
        else: title = raw_no_idx[:120]
    rid = hashlib.md5(f"{doi}|{_norm_title(title)}|{_norm_authors(authors)}|{year}".encode()).hexdigest()
    return BibRecord(id=rid, import_batch_id=batch_id, source_name=source_name,
        title=title, normalized_title=_norm_title(title), authors=authors, normalized_authors=_norm_authors(authors),
        year=year, journal=journal, doi=doi, document_type=doc_type, raw_reference=raw, imported_at=int(time.time()))


store = BibStore()

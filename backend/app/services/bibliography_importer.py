"""Multi-format bibliography importer.

Supports: RIS, BibTeX, CSV, Excel (xlsx), JSON, GB/T 7714 plain text.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".ris", ".bib", ".bibtex", ".csv", ".xlsx", ".xls", ".json", ".txt"}

DOI_PATTERN = re.compile(r"10\.\d{4,}/[^\s)\]）,，。；;]+")
YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")


def _extract_doi(text: str) -> str:
    m = DOI_PATTERN.search(text)
    return m.group(0).rstrip(".,;") if m else ""


def _extract_year(text: str) -> Optional[int]:
    m = YEAR_PATTERN.search(text)
    return int(m.group(0)) if m else None


def _clean_author(author: str) -> str:
    return re.sub(r"[\s,;，；]+$", "", author.strip()).strip()


class BibliographyImporter:
    """Import bibliographic records from various formats."""

    @staticmethod
    def detect_format(filename: str, content_preview: str = "") -> str:
        ext = Path(filename).suffix.lower()
        if ext in (".ris",):
            return "ris"
        if ext in (".bib", ".bibtex"):
            return "bibtex"
        if ext in (".csv",):
            return "csv"
        if ext in (".xlsx", ".xls"):
            return "xlsx"
        if ext in (".json",):
            return "json"
        if ext in (".txt",):
            if content_preview.strip().startswith("TY  -"):
                return "ris"
            if content_preview.strip().startswith("@"):
                return "bibtex"
            if content_preview.strip().startswith("[") or content_preview.strip().startswith("{"):
                return "json"
            return "gbt7714"
        return "unknown"

    def parse(self, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        fmt = self.detect_format(filename, file_bytes[:2000].decode("utf-8", errors="ignore"))
        if fmt == "ris":
            return self._parse_ris(file_bytes)
        elif fmt == "bibtex":
            return self._parse_bibtex(file_bytes)
        elif fmt == "csv":
            return self._parse_csv(file_bytes)
        elif fmt == "xlsx":
            return self._parse_xlsx(file_bytes)
        elif fmt == "json":
            return self._parse_json(file_bytes)
        elif fmt == "gbt7714":
            return self._parse_gbt7714(file_bytes)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    def _parse_ris(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8", errors="ignore")
        records: List[Dict[str, Any]] = []
        current: Dict[str, str] = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                if current and "ER" in [k.upper() for k in current.keys()]:
                    records.append(self._ris_to_record(current))
                    current = {}
                continue
            if len(line) < 6 or line[2:4] != "  -":
                continue
            tag = line[:2].upper()
            value = line[6:].strip()
            if tag == "AU":
                existing = current.get("AU", "")
                current["AU"] = (existing + "; " + value).strip("; ")
            elif tag == "KW":
                existing = current.get("KW", "")
                current["KW"] = (existing + "; " + value).strip("; ")
            else:
                current[tag] = value
        if current:
            records.append(self._ris_to_record(current))
        return records

    def _ris_to_record(self, ris: Dict[str, str]) -> Dict[str, Any]:
        authors_raw = ris.get("AU", "")
        authors = [_clean_author(a) for a in authors_raw.split(";") if a.strip()] if authors_raw else []
        title = ris.get("T1", "") or ris.get("TI", "") or ris.get("CT", "")
        doi = ris.get("DO", "") or _extract_doi(ris.get("UR", "") + ris.get("N2", ""))
        keywords_raw = ris.get("KW", "")
        keywords = [k.strip() for k in keywords_raw.split(";") if k.strip()] if keywords_raw else []
        year = _extract_year(ris.get("PY", "") or ris.get("Y1", ""))
        ref_type = {"JOUR": "J", "JFULL": "J", "CHAP": "M", "BOOK": "M", "CONF": "C", "THES": "D", "PAT": "P", "RPRT": "R", "NEWS": "N"}.get(ris.get("TY", "JOUR").upper(), "J")
        raw_ref = f"{authors_raw} ({year}). {title}. {ris.get('JO', '') or ris.get('T2', '')}, {ris.get('VL', '')}({ris.get('IS', '')}), {ris.get('SP', '')}-{ris.get('EP', '')}."

        return {
            "title": title, "authors": authors, "year": year,
            "journal": ris.get("JO", "") or ris.get("T2", ""),
            "publisher": ris.get("PB", ""), "volume": ris.get("VL", ""),
            "issue": ris.get("IS", ""), "pages": f"{ris.get('SP', '')}-{ris.get('EP', '')}".strip("-"),
            "doi": doi, "isbn": ris.get("SN", ""), "url": ris.get("UR", ""),
            "abstract": ris.get("N2", ""), "keywords": keywords,
            "source_platform": "ris_import", "language": "en" if not any('一' <= c <= '鿿' for c in title) else "zh",
            "ref_type": ref_type, "raw_reference": raw_ref,
        }

    def _parse_bibtex(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8", errors="ignore")
        records = []
        entries = re.split(r"@\w+\{", text, flags=re.IGNORECASE)
        for entry in entries:
            if not entry.strip() or entry.strip().startswith("%"):
                continue
            cite_key_end = entry.find(",")
            if cite_key_end < 0:
                continue
            fields_text = entry[cite_key_end + 1:]
            record: Dict[str, Any] = {}
            field_pat = re.compile(r'(\w+)\s*=\s*[{"]((?:[^{}"]|{[^{}]*})*)[}"]', re.DOTALL)
            for m in field_pat.finditer(fields_text):
                key = m.group(1).lower()
                value = m.group(2).strip().replace("\n", " ").replace("  ", " ")
                value = re.sub(r"\{([^{}]*)\}", r"\1", value)
                record[key] = value

            authors_str = record.get("author", "")
            authors = [a.strip() for a in re.split(r"\s+and\s+", authors_str)] if authors_str else []
            title = record.get("title", "")
            doi = record.get("doi", "") or _extract_doi(record.get("url", "") + record.get("note", ""))
            keywords = [k.strip() for k in record.get("keywords", "").split(",") if k.strip()]
            year = _extract_year(record.get("year", ""))
            raw_ref = f"{authors_str} ({year}). {title}. {record.get('journal', '')}, {record.get('volume', '')}({record.get('number', '')}), {record.get('pages', '')}."

            records.append({
                "title": title, "authors": authors, "year": year,
                "journal": record.get("journal", ""), "publisher": record.get("publisher", ""),
                "volume": record.get("volume", ""), "issue": record.get("number", ""),
                "pages": record.get("pages", ""), "doi": doi,
                "isbn": record.get("isbn", ""), "url": record.get("url", ""),
                "abstract": record.get("abstract", ""), "keywords": keywords,
                "source_platform": "bibtex_import",
                "language": "en" if not any('一' <= c <= '鿿' for c in title) else "zh",
                "ref_type": "J", "raw_reference": raw_ref,
            })
        return records

    def _parse_csv(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        records = []
        field_map = {
            "title": ["title", "题名", "题名", "标题", "文献标题"],
            "authors": ["authors", "author", "作者", "著者"],
            "year": ["year", "年份", "出版年", "发表年份"],
            "journal": ["journal", "期刊", "来源", "出版物"],
            "doi": ["doi", "DOI"],
            "volume": ["volume", "卷"],
            "issue": ["issue", "期", "number"],
            "pages": ["pages", "页码"],
            "url": ["url", "链接", "网址"],
            "abstract": ["abstract", "摘要"],
            "keywords": ["keywords", "关键词"],
        }
        for row in reader:
            rec: Dict[str, Any] = {}
            for target, candidates in field_map.items():
                for c in candidates:
                    if c in row and row[c]:
                        rec[target] = row[c].strip()
                        break
            if not rec.get("title"):
                continue
            authors_str = rec.get("authors", "")
            rec["authors"] = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []
            rec["year"] = _extract_year(str(rec.get("year", "")))
            rec["source_platform"] = "csv_import"
            rec["language"] = "en" if not any('一' <= c <= '鿿' for c in rec.get("title", "")) else "zh"
            rec["ref_type"] = "J"
            records.append(rec)
        return records

    def _parse_xlsx(self, data: bytes) -> List[Dict[str, Any]]:
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl is required for Excel import. Install with: pip install openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        records = []
        for row in rows[1:]:
            rec = {}
            for h, v in zip(headers, row):
                if v is not None and str(v).strip():
                    rec[h] = str(v).strip()
            if not rec:
                continue
            title = rec.get("title") or rec.get("题名") or rec.get("标题", "")
            if not title:
                continue
            authors_str = rec.get("authors") or rec.get("作者", "")
            rec["authors"] = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []
            rec["title"] = title
            rec["year"] = _extract_year(rec.get("year") or rec.get("年份", ""))
            rec["journal"] = rec.get("journal") or rec.get("期刊") or rec.get("来源", "")
            rec["doi"] = rec.get("doi") or rec.get("DOI", "")
            rec["source_platform"] = "xlsx_import"
            rec["language"] = "en" if not any('一' <= c <= '鿿' for c in title) else "zh"
            rec["ref_type"] = "J"
            records.append(rec)
        wb.close()
        return records

    def _parse_json(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8", errors="ignore")
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            items = list(parsed.values()) if not parsed.get("title") else [parsed]
        elif isinstance(parsed, list):
            items = parsed
        else:
            return []
        records = []
        for item in items:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            authors = item.get("authors", [])
            if isinstance(authors, str):
                authors = [a.strip() for a in authors.split(";") if a.strip()]
            title = item.get("title", "")
            records.append({
                "title": title, "authors": authors, "year": item.get("year"),
                "journal": item.get("journal", ""), "publisher": item.get("publisher", ""),
                "volume": item.get("volume", ""), "issue": item.get("issue", ""),
                "pages": item.get("pages", ""), "doi": item.get("doi", ""),
                "isbn": item.get("isbn", ""), "url": item.get("url", ""),
                "abstract": item.get("abstract", ""), "keywords": item.get("keywords", []),
                "source_platform": "json_import",
                "language": item.get("language", "en" if not any('一' <= c <= '鿿' for c in title) else "zh"),
                "ref_type": item.get("ref_type", "J"), "raw_reference": item.get("raw_reference", ""),
            })
        return records

    def _parse_gbt7714(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8", errors="ignore")
        return self.parse_gbt7714_text(text)

    @staticmethod
    def parse_gbt7714_text(text: str) -> List[Dict[str, Any]]:
        """Parse GB/T 7714 formatted reference text into structured records."""
        records = []
        gb_patterns = [
            (re.compile(r"\[(\d+)\]\s*"), None),
            (re.compile(r"^\d+[\.\、\s]"), None),
            (re.compile(r"(?<=[。.])\s*(?=[A-Z一-鿿])"), None),
        ]
        entries = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 10:
                continue
            entries.append(line)

        for entry in entries:
            ref_types = {
                "期刊": "[J]", "学位": "[D]", "专著": "[M]", "会议": "[C]",
                "报纸": "[N]", "专利": "[P]", "报告": "[R]", "标准": "[S]",
                "电子": "[EB/OL]", "网络": "[EB/OL]", "论文": "[D]",
            }
            ref_type = "J"
            for label, code in ref_types.items():
                if label in entry:
                    ref_type = {"[J]": "J", "[M]": "M", "[D]": "D", "[C]": "C",
                                "[N]": "N", "[P]": "P", "[R]": "R", "[S]": "S",
                                "[EB/OL]": "EB/OL"}.get(code, "J")
                    break

            doi = _extract_doi(entry)
            year = _extract_year(entry)
            authors = []
            title = entry[:200]
            journal = ""

            m = re.match(r"^([^[.\d].*?)[\.\s]+", entry)
            if m:
                first_part = m.group(1)
                if re.search(r"[一-鿿]", first_part) and len(first_part) < 80:
                    authors = [a.strip() for a in re.split(r"[,，;；]", first_part) if a.strip()]

            j_match = re.search(r"\[J\].*?\.\s*(.+?)(?:,|，|\d{4})", entry)
            if j_match:
                journal = j_match.group(1).strip()[:100]

            t_match = re.search(r"\.\s*(.+?)\s*\[[JMCDNPRS]", entry)
            if t_match:
                title = t_match.group(1).strip()[:300]

            records.append({
                "title": title, "authors": authors, "year": year,
                "journal": journal, "doi": doi,
                "language": "zh" if any('一' <= c <= '鿿' for c in entry) else "en",
                "ref_type": ref_type, "raw_reference": entry,
                "source_platform": "gbt7714_import",
            })
        return records

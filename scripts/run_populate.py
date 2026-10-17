"""Run paper population from populate_papers.py + papers_extra.json"""
import json, hashlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "backend" / "data" / "public" / "documents"
META_FILE = ROOT / "backend" / "data" / "public" / "metadata.json"
DOC_DIR.mkdir(parents=True, exist_ok=True)

# Load existing metadata
meta = {}
if META_FILE.exists():
    try: meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    except: pass

# Load extra papers
extra_path = ROOT / "scripts" / "papers_extra.json"
extra_papers = json.loads(extra_path.read_text(encoding="utf-8"))

# Also load built-in papers from populate_papers.py
# Run the script to get PAPERS list
sys.path.insert(0, str(ROOT / "scripts"))
from populate_papers import PAPERS

all_papers = PAPERS + extra_papers

added = 0
for paper in all_papers:
    fname = paper["title"].replace("/", "_").replace("\\", "_").replace(":", "：")[:120] + ".txt"
    filepath = DOC_DIR / fname

    content = (
        f"标题：{paper['title']}\n"
        f"作者：{paper['authors']}\n"
        f"期刊：{paper['journal']} ({paper['year']})\n"
        f"关键词：{'；'.join(paper['keywords'])}\n\n"
        f"摘要：{paper['abstract']}\n"
    )

    if not filepath.exists():
        filepath.write_text(content, encoding="utf-8")

    file_hash = hashlib.md5(filepath.read_bytes()).hexdigest()
    meta[fname] = {
        "title": paper["title"],
        "authors": paper.get("authors", ""),
        "journal": paper.get("journal", ""),
        "year": paper.get("year", ""),
        "category": "论文",
        "tags": paper.get("keywords", []),
        "discipline": "公共管理",
        "main_topic": paper["keywords"][0] if paper.get("keywords") else "",
        "size": filepath.stat().st_size,
        "file_hash": file_hash,
    }
    added += 1

META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Added {added} papers")
print(f"Total knowledge base: {len(meta)} documents")

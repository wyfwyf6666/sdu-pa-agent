"""Local bibliography API."""
from __future__ import annotations
import logging, shutil, tempfile
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, Depends
from fastapi.responses import JSONResponse
from backend.app.dependencies.auth import get_current_user
from backend.app.models.user import User
from backend.app.services.local_bibliography import BibStore, import_file, match_reference, DB_PATH

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/bibliography", tags=["bibliography"])

@router.post("/import")
async def bib_import(file: UploadFile = File(...), source_name: str = Form("CNKI"),
    institution_source: str = Form(""), current_user: User = Depends(get_current_user)):
    s = Path(file.filename or "").suffix.lower()
    if s not in {".txt", ".csv", ".xlsx", ".xls", ".json"}:
        raise HTTPException(400, f"不支持的文件类型：{s}")
    try:
        content = await file.read()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / (file.filename or "upload")
            p.write_bytes(content)
            r = import_file(p, source_name, institution_source)
            r["success"] = True
            return JSONResponse(content=r)
    except Exception as e:
        LOGGER.exception("import failed")
        raise HTTPException(500, detail=str(e))

@router.get("/imports")
async def bib_imports(current_user: User = Depends(get_current_user)):
    s = BibStore()
    return {"items": s.list_batches(), "total_records": s.count()}

@router.get("/search")
async def bib_search(q: str = Query(""), limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user)):
    s = BibStore()
    return {"query": q, "items": s.search(q, limit)}

@router.delete("/imports/{batch_id}")
async def bib_delete_batch(batch_id: str, current_user: User = Depends(get_current_user)):
    return BibStore().delete_batch(batch_id)

@router.get("/debug")
async def bib_debug(current_user: User = Depends(get_current_user)):
    s = BibStore()
    return {"db_path": str(DB_PATH), "db_exists": DB_PATH.exists(), "total_records": s.count(), "total_batches": len(s.list_batches())}

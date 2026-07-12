"""Read-only observation surface for character growth (Brief 64)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from admin.auth import require_scopes
from admin.routers.memory import _resolve_char_id

router = APIRouter()


def _interest_dir(interest_id: str, char_id: str) -> Path:
    try:
        from core.sandbox import get_paths
        return get_paths().growth_works_dir(interest_id, char_id=char_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="非法 interest_id") from exc


def _read_index(interest_id: str, char_id: str) -> list[dict]:
    path = _interest_dir(interest_id, char_id) / "index.json"
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


@router.get("/growth/interests", summary="读取角色兴趣与学习进度")
async def get_interests(
    char_id: str | None = None,
    _auth=Depends(require_scopes("state.read")),
):
    from core.growth import interest_state
    resolved = _resolve_char_id(char_id)
    interests = interest_state.load(resolved).get("interests", [])
    return {"char_id": resolved, "interests": interests, "count": len(interests)}


@router.get("/growth/works/{interest_id}", summary="列出某兴趣作品索引")
async def get_works(
    interest_id: str,
    char_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    before: str = "",
    _auth=Depends(require_scopes("memory.read")),
):
    resolved = _resolve_char_id(char_id)
    entries = _read_index(interest_id, resolved)
    if before:
        entries = [entry for entry in entries if str(entry.get("date", "")) < before]
    entries = entries[-limit:]
    return {"char_id": resolved, "interest_id": interest_id, "entries": entries, "count": len(entries)}


@router.get("/growth/works/{interest_id}/{filename}", summary="读取一件练习作品全文")
async def get_work(
    interest_id: str,
    filename: str,
    char_id: str | None = None,
    _auth=Depends(require_scopes("memory.read")),
):
    resolved = _resolve_char_id(char_id)
    if Path(filename).name != filename or not filename.endswith(".md"):
        raise HTTPException(status_code=422, detail="非法作品文件名")
    root = _interest_dir(interest_id, resolved)
    if filename not in {str(x.get("file")) for x in _read_index(interest_id, resolved)}:
        raise HTTPException(status_code=404, detail="作品不存在")
    path = root / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="作品文件不存在")
    try:
        return {"char_id": resolved, "interest_id": interest_id, "file": filename, "content": path.read_text(encoding="utf-8")}
    except OSError:
        raise HTTPException(status_code=404, detail="作品文件不可读")


@router.get("/growth/notes/{interest_id}", summary="读取某兴趣技巧笔记")
async def get_notes(
    interest_id: str,
    char_id: str | None = None,
    _auth=Depends(require_scopes("memory.read")),
):
    try:
        from core.growth import notes
        resolved = _resolve_char_id(char_id)
        entries = notes.load(interest_id, char_id=resolved)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="非法 interest_id") from exc
    return {"char_id": resolved, "interest_id": interest_id, "entries": entries, "count": len(entries)}


@router.get("/growth/practice-log", summary="读取练习相关 fixation 日志")
async def get_practice_log(
    limit: int = Query(100, ge=1, le=500),
    before: float | None = None,
    _auth=Depends(require_scopes("state.read")),
):
    from core.sandbox import get_paths
    path = get_paths().fixation_log()
    if not path.exists():
        return {"entries": [], "count": 0}
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or "practice" not in json.dumps(row, ensure_ascii=False).lower():
            continue
        ts = row.get("ts")
        if before is not None and isinstance(ts, (int, float)) and ts >= before:
            continue
        entries.append(row)
    entries = entries[-limit:]
    return {"entries": entries, "count": len(entries)}

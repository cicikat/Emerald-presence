"""
关系事实表管理路由

提供 per-user relationship_facts.yaml 的增删改查及审核接口。
路径：/relationship-facts/{uid}

审核门：pending → confirmed 需显式调用 /confirm；拒绝调用 /reject（→ archived）。
只有 confirmed 条目进入 5.5_lore 注入。
"""

from datetime import date
from typing import List, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin.auth import verify_token
from core.relationship_facts import load, save, run_address_suggester
from core.sandbox import safe_user_id

router = APIRouter()


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _get_active_char_id() -> str:
    """读取当前 active_character，用于未指定 char_id 时的默认值。"""
    try:
        import json
        from core.sandbox import get_paths
        assets = json.loads(get_paths().active_prompt_assets().read_text(encoding="utf-8"))
        return assets.get("active_character", "")
    except Exception:
        return ""


def _resolve_char_id(char_id: Optional[str]) -> str:
    cid = char_id or _get_active_char_id()
    if not cid:
        raise HTTPException(status_code=400, detail="无法确定 char_id，请显式传入")
    return cid


# ── 数据模型 ──────────────────────────────────────────────────────────────────

class FactIn(BaseModel):
    keywords:        List[str]
    content:         str
    enabled:         bool = True    # 实际注入闸门（True=注入，False=不注入）
    status:          str = "confirmed"   # 语义注解，方便面板过滤
    confidence:      float = 1.0
    source:          str = "manual"
    insertion_order: int = 60
    regex:           bool = False


# ── 路由 ─────────────────────────────────────────────────────────────────────

@router.get("/relationship-facts/{uid}", summary="列出用户的关系事实")
async def list_facts(
    uid: str,
    status: Optional[str] = None,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    """
    列出指定用户的关系事实。
    ?status=pending  — 只看待审核条目（带证据）
    ?status=confirmed — 只看已确认（会注入 prompt）
    不传 status 则返回全部。
    """
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    if status:
        facts = [f for f in facts if f.get("status") == status]
    return {"uid": uid, "char_id": cid, "count": len(facts), "facts": facts}


@router.post("/relationship-facts/{uid}", summary="手动添加关系事实")
async def add_fact(
    uid: str,
    entry: FactIn,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    """手动创建一条关系事实（默认 status=confirmed，创建即生效）。"""
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    today = date.today().isoformat()
    new_fact = {
        "keywords":        entry.keywords,
        "content":         entry.content,
        "enabled":         entry.enabled,   # 手动创建默认 True（即时生效）
        "status":          entry.status,
        "confidence":      entry.confidence,
        "source":          entry.source,
        "first_seen":      today,
        "last_seen":       today,
        "hit_count":       0,
        "insertion_order": entry.insertion_order,
        "regex":           entry.regex,
    }
    facts.append(new_fact)
    save(uid, facts, char_id=cid)
    return {"message": "条目已添加", "index": len(facts) - 1, "fact": new_fact}


@router.put("/relationship-facts/{uid}/{index}", summary="修改关系事实")
async def update_fact(
    uid: str,
    index: int,
    entry: FactIn,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    if index < 0 or index >= len(facts):
        raise HTTPException(status_code=404, detail=f"条目下标 {index} 不存在")
    old = facts[index]
    facts[index] = {
        **old,
        "keywords":        entry.keywords,
        "content":         entry.content,
        "enabled":         entry.enabled,
        "status":          entry.status,
        "confidence":      entry.confidence,
        "source":          entry.source,
        "insertion_order": entry.insertion_order,
        "regex":           entry.regex,
    }
    save(uid, facts, char_id=cid)
    return {"message": f"条目 {index} 已更新"}


@router.post("/relationship-facts/{uid}/{index}/confirm", summary="确认 pending 条目（→ confirmed）")
async def confirm_fact(
    uid: str,
    index: int,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    """
    将指定下标的 pending 条目设为 confirmed（enabled:true），即时生效。
    实际闸门是 enabled:true；status=confirmed 为语义注解。
    """
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    if index < 0 or index >= len(facts):
        raise HTTPException(status_code=404, detail=f"条目下标 {index} 不存在")
    facts[index]["enabled"] = True
    facts[index]["status"] = "confirmed"
    facts[index]["last_seen"] = date.today().isoformat()
    save(uid, facts, char_id=cid)
    return {"message": f"条目 {index} 已确认（enabled=true, status=confirmed）", "fact": facts[index]}


@router.post("/relationship-facts/{uid}/{index}/reject", summary="拒绝 pending 条目（→ archived）")
async def reject_fact(
    uid: str,
    index: int,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    """将指定下标的条目设为 archived（enabled:false，不再注入，不删除，可追溯）。"""
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    if index < 0 or index >= len(facts):
        raise HTTPException(status_code=404, detail=f"条目下标 {index} 不存在")
    facts[index]["enabled"] = False
    facts[index]["status"] = "archived"
    save(uid, facts, char_id=cid)
    return {"message": f"条目 {index} 已拒绝（enabled=false, status=archived）"}


@router.delete("/relationship-facts/{uid}/{index}", summary="删除关系事实")
async def delete_fact(
    uid: str,
    index: int,
    char_id: Optional[str] = None,
    auth=Depends(verify_token),
):
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    facts = load(uid, char_id=cid)
    if index < 0 or index >= len(facts):
        raise HTTPException(status_code=404, detail=f"条目下标 {index} 不存在")
    removed = facts.pop(index)
    save(uid, facts, char_id=cid)
    return {"message": f"条目 {index} 已删除", "removed_keywords": removed.get("keywords", [])}


@router.post("/relationship-facts/{uid}/run-suggester", summary="运行称呼建议器")
async def run_suggester(
    uid: str,
    char_id: Optional[str] = None,
    days: int = 30,
    freq_threshold: int = 15,
    min_start_count: int = 3,
    auth=Depends(verify_token),
):
    """
    手动触发称呼频次建议器：扫描近 days 天 event_log，
    为高频固定称呼产出 pending 建议条目（带证据）。
    产出的条目需在面板中手动 confirm 后才会注入 prompt。
    """
    uid = safe_user_id(uid)
    cid = _resolve_char_id(char_id)
    new_facts = run_address_suggester(
        uid, cid,
        days=days,
        freq_threshold=freq_threshold,
        min_start_count=min_start_count,
    )
    return {
        "message": f"建议器完成，新增 {len(new_facts)} 条 pending 条目",
        "new_pending": new_facts,
    }

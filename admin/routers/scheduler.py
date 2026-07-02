"""
调度器管理路由
提供调度器状态查询、配置读写、手动触发等接口
"""

from fastapi import APIRouter, Depends, HTTPException

from admin.auth import verify_token
from core.config_loader import get_config, reload_config

router = APIRouter()


def _sched_cfg() -> dict:
    return get_config().get("scheduler", {})


def _save_sched_cfg(new_sched: dict):
    """将修改后的 scheduler 节写回 config.yaml"""
    import yaml
    from pathlib import Path
    path = Path("config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        full = yaml.safe_load(f) or {}
    full["scheduler"] = new_sched
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(full, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    reload_config()


# ── 状态 ──────────────────────────────────────────────────────────────────────

@router.get("/scheduler/status", summary="获取调度器触发状态")
async def get_scheduler_status(auth=Depends(verify_token)):
    """返回各触发器的冷却状态和上次触发时间"""
    from core.scheduler import get_status
    return {
        "enabled": _sched_cfg().get("enabled", True),
        "triggers": get_status(),
    }


@router.get("/scheduler/proactive-ledger", summary="获取 ProactiveLedger 账本快照")
async def get_proactive_ledger(auth=Depends(verify_token)):
    """
    统一发送预算/记账观测端点（CC 任务 19 · B）。

    返回 effective_gap_seconds（当前内存生效的全局间隔，可与 config.yaml 的
    global_proactive_min_gap_seconds 对比核实是否已热加载）、next_allowed_ts、
    今日已发条数/预算、最近 3 条发送 gist。"止血生效没有"以后一眼可查。
    """
    from core.scheduler.proactive_ledger import snapshot
    return snapshot()


# ── 配置读写 ──────────────────────────────────────────────────────────────────

@router.get("/scheduler/config", summary="读取调度器配置")
async def get_sched_config(auth=Depends(verify_token)):
    """
    PUT 侧接受 global_proactive_min_gap_hours（小时，前端易用单位），
    落盘/消费统一走 global_proactive_min_gap_seconds。GET 侧补一个派生的
    _hours 字段做对称回显，避免调用方 PUT hours 后在 GET 里读不到同名字段。

    D5：额外并列返回 effective_gap_seconds（ProactiveLedger 当前实际使用的内存值）
    与文件值 global_proactive_min_gap_seconds。A1 的 config 热加载落地后两者应恒
    一致——若不一致，说明热加载链路出了问题，需要手动 reload_config()。
    """
    cfg = dict(_sched_cfg())
    seconds = cfg.get("global_proactive_min_gap_seconds")
    if seconds is not None:
        cfg["global_proactive_min_gap_hours"] = round(float(seconds) / 3600, 4)
    from core.scheduler.proactive_ledger import snapshot as _ledger_snapshot
    effective = _ledger_snapshot()["effective_gap_seconds"]
    cfg["effective_gap_seconds"] = effective
    cfg["effective_gap_reload_needed"] = (
        seconds is not None and float(effective) != float(seconds)
    )
    return cfg


@router.put("/scheduler/config", summary="更新调度器配置")
async def put_sched_config(body: dict, auth=Depends(verify_token)):
    """
    支持局部更新，只传需要改的字段。
    signatures 字段若传入则整体替换。
    """
    cfg = dict(_sched_cfg())

    bool_fields = [
        "enabled", "morning_greeting", "night_reminder", "random_message",
        "daily_journal", "period_reminder", "diary_reminder", "diary_inject",
        "presence_nag",
    ]
    for f in bool_fields:
        if f in body:
            cfg[f] = bool(body[f])

    if "owner_id" in body:
        cfg["owner_id"] = str(body["owner_id"]).strip()

    if "presence_nag_minutes" in body:
        try:
            minutes = int(body["presence_nag_minutes"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="presence_nag_minutes 必须是正整数")
        if minutes <= 0:
            raise HTTPException(status_code=422, detail="presence_nag_minutes 必须是正整数")
        cfg["presence_nag_minutes"] = minutes

    if "global_proactive_min_gap_hours" in body:
        try:
            hours = float(body["global_proactive_min_gap_hours"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="global_proactive_min_gap_hours 必须是数字")
        if not (0 < hours <= 24):
            raise HTTPException(status_code=422, detail="global_proactive_min_gap_hours 需在 (0, 24] 小时内")
        cfg["global_proactive_min_gap_seconds"] = int(round(hours * 3600))

    if "signatures" in body:
        sigs = body["signatures"]
        if not isinstance(sigs, list):
            raise HTTPException(status_code=422, detail="signatures 必须为数组")
        cfg["signatures"] = [str(s).strip() for s in sigs if str(s).strip()]

    _save_sched_cfg(cfg)
    return {"message": "调度器配置已保存", "config": cfg}


@router.delete("/scheduler/signatures", summary="删除一条签名")
async def delete_signature(body: dict, auth=Depends(verify_token)):
    text = str(body.get("text", "")).strip()
    cfg = dict(_sched_cfg())
    sigs = [s for s in cfg.get("signatures", []) if s != text]
    cfg["signatures"] = sigs
    _save_sched_cfg(cfg)
    return {"message": "已删除", "signatures": sigs}


# ── 手动触发 ─────────────────────────────────────────────────────────────────

@router.post("/scheduler/trigger/{name}", summary="手动触发指定动作")
async def manual_trigger(name: str, auth=Depends(verify_token)):
    """
    可触发的名称：
      morning_greeting / night_reminder / random_message
    """
    from core.scheduler import manual_trigger as _trigger
    result = await _trigger(name)
    return {"message": result}


# ── sensor_aware 审计 ─────────────────────────────────────────────────────────

@router.get("/scheduler/sensor_aware/audit", summary="获取 sensor_aware 最近决策审计日志")
async def get_sensor_aware_audit(n: int = 50, auth=Depends(verify_token)):
    """
    返回最近 N 条 sensor_aware 完整决策快照（新→旧）。
    N 最大 50，默认 50。

    每条 entry 包含：tick_at、candidates、picked_event、judge_input_prompt、
    judge_output_raw、judge_score、judge_reason、tier、candidate_behavior、
    pipeline_send_prompt、pipeline_send_reply、action_packet、final_stage、
    cooldown_remaining_seconds。
    """
    try:
        from core.scheduler.triggers.sensor_aware_audit import get_recent
        entries = get_recent(min(max(n, 1), 50))
    except Exception:
        entries = []
    return {"count": len(entries), "entries": entries}

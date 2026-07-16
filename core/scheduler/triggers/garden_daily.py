"""garden_daily — 每天扫一次 harvest 过期 / handle / vase 枯萎，关键事件让角色说话。"""

import logging
import time

from core.scheduler.loop import _is_ready, _mark
from core.garden import manager as garden_manager

logger = logging.getLogger(__name__)

GARDEN_EVENT_PROPOSAL_TTL_SECONDS = 24 * 3600
_LAST_DAILY_EVENTS: list[dict] = []


def _active_char_id() -> str | None:
    try:
        import json as _j
        raw = _j.loads(
            __import__("core.sandbox", fromlist=["get_paths"]).get_paths()
            .active_prompt_assets().read_text(encoding="utf-8")
        )
        cid = (raw.get("active_character") or "").strip()
    except Exception:
        logger.warning("[garden_daily] active_prompt_assets 读取失败，跳过本次 tick")
        return None

    if not cid:
        logger.warning("[garden_daily] active_character 为空，跳过本次 tick")
        return None

    try:
        from core.asset_registry import get_registry
        get_registry().resolve(cid, "character")
    except ValueError:
        logger.warning("[garden_daily] active_character %r 不在注册表，跳过本次 tick", cid)
        return None

    return cid


async def _check_garden_daily() -> None:
    if not _is_ready("garden_daily"):
        return
    _mark("garden_daily")

    char_id = _active_char_id()
    if char_id is None:
        return
    try:
        events = garden_manager.daily_check(char_id=char_id)
    except Exception:
        logger.exception("[garden] daily_check failed")
        return

    # 状态变更已在 daily_check() 内落地；发言只记录事件供 propose_garden_* 走
    # gating 统一决策发送（D4：删除被 EXECUTE_MODE="live" 挡死的 legacy _emit
    # for-loop，legacy_tick_should_send() 此前恒 False，_emit 从未被调用过）。
    for event in events:
        _remember_daily_event(event)


def _remember_daily_event(event: dict) -> None:
    _LAST_DAILY_EVENTS.append({**event, "received_at": time.time()})
    del _LAST_DAILY_EVENTS[:-20]


def _proposal_for(trigger_name: str, event_type: str, action: str | None = None, ctx: dict | None = None):
    ctx = ctx or {}
    now_ts = float(ctx.get("now_ts") or time.time())
    events = ctx.get("garden_daily_events") or _LAST_DAILY_EVENTS
    matches = []
    for event in events:
        if event.get("type") != event_type:
            continue
        if action is not None and event.get("handle_action") != action:
            continue
        if now_ts - float(event.get("received_at") or 0) <= GARDEN_EVENT_PROPOSAL_TTL_SECONDS:
            matches.append(event)
    if not matches:
        return None

    from core.scheduler.gating import TriggerProposal
    from core.scheduler.state_machine import TriggerState
    from core.scheduler.urgency import UrgencyTier, urgency_in_tier

    picked = max(matches, key=lambda event: float(event.get("received_at") or 0))
    newest = float(picked.get("received_at") or 0)
    ratio = 1 - min(1.0, max(0.0, (now_ts - newest) / GARDEN_EVENT_PROPOSAL_TTL_SECONDS))
    return TriggerProposal(
        trigger_name=trigger_name,
        urgency=urgency_in_tier(UrgencyTier.REACTIVE, ratio),
        topic_source="mood_match",
        requires_state=[TriggerState.QUIET],
        bypass_state_machine=False,
        execute=_make_garden_daily_execute(trigger_name, picked),
    )


def propose_garden_harvest_expired(ctx: dict | None = None):
    return _proposal_for("garden_harvest_expired", "harvest_expired", ctx=ctx)


def propose_garden_vase_wilted(ctx: dict | None = None):
    return _proposal_for("garden_vase_wilted", "vase_wilted", ctx=ctx)


def propose_garden_handle_gift(ctx: dict | None = None):
    return _proposal_for("garden_handle_gift", "harvest_handle", action="gift", ctx=ctx)


def propose_garden_handle_self(ctx: dict | None = None):
    """G4：只覆盖 vase 分支——dry/ask 已改为落 history 纪念记录，不再主动发消息
    （DESIGN.md §十一 决策 8："ask 与 dry 不发消息"）。"""
    ctx = ctx or {}
    now_ts = float(ctx.get("now_ts") or time.time())
    events = ctx.get("garden_daily_events") or _LAST_DAILY_EVENTS
    self_events = [
        event for event in events
        if event.get("type") == "harvest_handle"
        and event.get("handle_action") == "vase"
        and now_ts - float(event.get("received_at") or 0) <= GARDEN_EVENT_PROPOSAL_TTL_SECONDS
    ]
    if not self_events:
        return None
    return _proposal_for(
        "garden_handle_self",
        "harvest_handle",
        action="vase",
        ctx={**ctx, "garden_daily_events": self_events},
    )


def _register_proposers() -> None:
    from core.scheduler.proposer_registry import register_proposer

    register_proposer("garden_harvest_expired", propose_garden_harvest_expired)
    register_proposer("garden_handle_gift", propose_garden_handle_gift)
    register_proposer("garden_handle_self", propose_garden_handle_self)
    register_proposer("garden_vase_wilted", propose_garden_vase_wilted)


_register_proposers()


def _garden_daily_prompt(trigger_name: str, event: dict) -> str:
    name = event.get("name", "?")
    if trigger_name == "garden_harvest_expired":
        return f"（你发现那株{name}放太久枯掉了，悄悄处理掉了。）"
    if trigger_name == "garden_vase_wilted":
        return f"（花瓶里那株{name}枯掉了，你默默把它收了。）"
    if trigger_name == "garden_handle_gift":
        language = event.get("language", "")
        tail = f"——{language}" if language else ""
        return f"（你想把那株{name}送给她{tail}。）"
    # garden_handle_self：G4 之后只有 vase 分支会走到这里（dry/ask 不再发消息）。
    return f"（你把那株{name}放进了花瓶，没有特别说什么。）"


def _make_garden_daily_execute(trigger_name: str, event: dict):
    async def execute(*, dry_run: bool):
        from core.scheduler.execution import execute_prompt

        return await execute_prompt(
            trigger_name=trigger_name,
            prompt_factory=lambda: _garden_daily_prompt(trigger_name, event),
            dry_run=dry_run,
            would_mark=[trigger_name],
            reads_cache_ok=True,
            recall_policy="none",
        )

    return execute

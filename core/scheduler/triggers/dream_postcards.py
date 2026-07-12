"""Daily archive-only dream-postcard mail delivery proposer."""
from __future__ import annotations

def propose(ctx: dict | None = None):
    ctx = ctx or {}
    from core.scheduler.loop import _active_char_id_or_none
    char_id = str(ctx.get("char_id") or _active_char_id_or_none() or "")
    if not char_id:
        return None
    from core.dream.postcard import _load_schedule
    from datetime import date
    if not any(not x.get("sent") and str(x.get("scheduled_date", "")) <= date.today().isoformat() for x in _load_schedule(char_id)):
        return None
    from core.scheduler.gating import TriggerProposal
    from core.scheduler.state_machine import TriggerState
    from core.scheduler.urgency import UrgencyTier, urgency_in_tier
    async def execute(*, dry_run: bool):
        from core.scheduler.execution import ExecuteResult
        if not dry_run:
            from core.dream.postcard import deliver_due_postcards
            await deliver_due_postcards(char_id=char_id)
        return ExecuteResult(trigger_name="dream_postcards", would_send_prompt="", would_mark=[], dry_run=dry_run, sent=False)
    return TriggerProposal(trigger_name="dream_postcards", urgency=urgency_in_tier(UrgencyTier.FILLER, .1), topic_source="dream_postcards", requires_state=[TriggerState.QUIET], bypass_state_machine=False, execute=execute)

def _register_proposers():
    from core.scheduler.proposer_registry import register_proposer
    register_proposer("dream_postcards", propose)

_register_proposers()

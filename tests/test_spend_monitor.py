import json
import time
from datetime import datetime

import pytest


def _cfg(*, enabled=True, cap=100, providers=None):
    return {"spend": {"enabled": enabled, "daily_cap": cap, "monthly_cap": cap,
            "payee_whitelist": ["deepseek"], "balance_providers": providers or []}}


def test_disabled_budget_rejects_without_ledger(sandbox, monkeypatch):
    monkeypatch.setattr("core.config_loader.get_config", lambda: _cfg(enabled=False))
    from core.actions.spend_ledger import check_budget
    assert check_budget("api_topup", "deepseek", 10) == (False, "disabled")
    assert not sandbox.spend_ledger().exists()


def test_confirmed_rows_enforce_daily_and_monthly_caps(sandbox, monkeypatch):
    monkeypatch.setattr("core.config_loader.get_config", lambda: _cfg(cap=50))
    from core.actions import spend_ledger
    assert spend_ledger.append(action="api_topup", payee="deepseek", amount=45, status="confirmed", origin="scheduler")
    assert spend_ledger.check_budget("api_topup", "deepseek", 10) == (False, "daily_cap")
    assert spend_ledger.check_budget("api_topup", "elsewhere", 1) == (False, "payee_not_whitelisted")


@pytest.mark.asyncio
async def test_low_balance_proposes_notifies_and_traces(sandbox, monkeypatch):
    import core.scheduler.triggers.spend_monitor as monitor
    provider = {"name": "deepseek", "threshold": 10, "topup_amount": 20, "topup_url": "https://pay.example"}
    monkeypatch.setattr("core.config_loader.get_config", lambda: _cfg(providers=[provider]))
    monkeypatch.setattr(monitor, "_recently_notified", lambda _p: False)
    async def balance(_p): return 2
    async def notify(_uid, _text): return True
    monkeypatch.setattr(monitor.api_balance, "fetch_balance", balance)
    monkeypatch.setattr(monitor, "_notify", notify)
    monkeypatch.setattr("core.scheduler.loop._is_ready", lambda _n: True)
    monkeypatch.setattr("core.scheduler.loop._mark", lambda _n: None)
    monkeypatch.setattr("core.scheduler.loop._owner_id", lambda: "u1")
    await monitor._check_spend_monitor()
    rows = [json.loads(x) for x in sandbox.spend_ledger().read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in rows] == ["proposed", "notified"]


@pytest.mark.asyncio
async def test_ledger_failure_stops_before_notification(sandbox, monkeypatch):
    import core.scheduler.triggers.spend_monitor as monitor
    provider = {"name": "deepseek", "threshold": 10, "topup_amount": 20}
    monkeypatch.setattr("core.config_loader.get_config", lambda: _cfg(providers=[provider]))
    monkeypatch.setattr(monitor, "_recently_notified", lambda _p: False)
    async def balance(_p): return 2
    monkeypatch.setattr(monitor.api_balance, "fetch_balance", balance)
    monkeypatch.setattr(monitor.spend_ledger, "append", lambda **_kw: None)
    notified = False
    async def notify(*_args):
        nonlocal notified
        notified = True
        return True
    monkeypatch.setattr(monitor, "_notify", notify)
    monkeypatch.setattr("core.scheduler.loop._is_ready", lambda _n: True)
    monkeypatch.setattr("core.scheduler.loop._mark", lambda _n: None)
    monkeypatch.setattr("core.scheduler.loop._owner_id", lambda: "u1")
    await monitor._check_spend_monitor()
    assert notified is False

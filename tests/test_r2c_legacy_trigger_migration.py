"""
tests/test_r2c_legacy_trigger_migration.py

R2-C: 全量发言 trigger 已迁移到 gating/proposer 路径，legacy 安全网已删除。

覆盖：
1. _pipeline_send 中无 legacy 安全网（_legacy_active_window_blocks / _legacy_dnd_blocks 已删）
2. MIGRATED_TRIGGERS 与注册的 proposer trigger_names 一致
3. Legacy speaking _check_* 函数在 live 模式下通过 legacy_tick_should_send() 让路（不发言）
4. Maintenance tick 不在 MIGRATED_TRIGGERS 中（不受发言 gating 影响）
5. execute_prompt 只在 sent=True 后才 _mark（未发送不 mark）
6. gating._decide 是发言决策唯一权威；_pipeline_send 不重新过滤
7. 发言 trigger 进入 proposer 候选流、不绕过 gating 直接 _pipeline_send
8. 被 gating 阻止的 trigger 不 mark
9. high-priority/exempt 语义通过 gating 保持
10. _HIGH_PRIORITY_TRIGGERS 常量仍存在（仅文档/断言用）
"""

from __future__ import annotations

import inspect
import pathlib
import time
from types import SimpleNamespace
from typing import Optional

import pytest

ROOT = pathlib.Path(__file__).parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _FakePipeline:
    async def fetch_context(self, uid, query):
        return {}

    def build_prompt(self, uid, prompt, context, **kwargs):
        return [{"role": "user", "content": prompt}], {}

    async def run_llm(self, messages):
        return "reply"


def _make_proposal(trigger_name: str, urgency: float = 0.5):
    from core.scheduler.gating import TriggerProposal
    from core.scheduler.state_machine import TriggerState
    return TriggerProposal(
        trigger_name=trigger_name,
        urgency=urgency,
        topic_source="test",
        requires_state=[TriggerState.QUIET],
    )


def _patch_gating_env(monkeypatch, *, user_active: bool, dnd_active: bool):
    import core.scheduler.loop as _loop
    import core.scheduler.triggers.dnd as _dnd
    monkeypatch.setattr(_loop, "_user_active_recently", lambda: user_active)
    monkeypatch.setattr(_dnd, "is_dnd", lambda uid: dnd_active)
    from core.scheduler.state_machine import TriggerState
    monkeypatch.setattr("core.scheduler.gating.get_current_state", lambda uid: TriggerState.QUIET)
    monkeypatch.setattr("core.scheduler.gating.is_trigger_ready", lambda name: True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _pipeline_send 中无 legacy 安全网
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineSendNoSafetyNet:
    """R2-C: _pipeline_send 不包含 legacy 安全网代码。"""

    def test_no_legacy_active_window_blocks_call(self):
        import core.scheduler.loop as loop
        src = inspect.getsource(loop._pipeline_send)
        assert "_legacy_active_window_blocks" not in src, (
            "_legacy_active_window_blocks 仍存在于 _pipeline_send — R2-C 要求删除"
        )

    def test_no_legacy_dnd_blocks_call(self):
        import core.scheduler.loop as loop
        src = inspect.getsource(loop._pipeline_send)
        assert "_legacy_dnd_blocks" not in src, (
            "_legacy_dnd_blocks 仍存在于 _pipeline_send — R2-C 要求删除"
        )

    def test_legacy_active_window_blocks_not_in_module(self):
        import core.scheduler.loop as loop
        assert not hasattr(loop, "_legacy_active_window_blocks"), (
            "loop._legacy_active_window_blocks 仍存在 — R2-C 要求删除"
        )

    def test_legacy_dnd_blocks_not_in_module(self):
        import core.scheduler.loop as loop
        assert not hasattr(loop, "_legacy_dnd_blocks"), (
            "loop._legacy_dnd_blocks 仍存在 — R2-C 要求删除"
        )

    def test_high_priority_triggers_constant_still_exists(self):
        """_HIGH_PRIORITY_TRIGGERS 保留用于文档/测试断言（不参与运行时决策）。"""
        import core.scheduler.loop as loop
        assert hasattr(loop, "_HIGH_PRIORITY_TRIGGERS")
        assert isinstance(loop._HIGH_PRIORITY_TRIGGERS, frozenset)
        assert len(loop._HIGH_PRIORITY_TRIGGERS) > 0

    def test_pipeline_send_has_kind_guard(self):
        """_pipeline_send 仍有 _assert_trigger_outlet_kind kind 门禁。"""
        import core.scheduler.loop as loop
        src = inspect.getsource(loop._pipeline_send)
        assert "_assert_trigger_outlet_kind" in src


# ─────────────────────────────────────────────────────────────────────────────
# 2. MIGRATED_TRIGGERS 与 proposer 注册集合一致
# ─────────────────────────────────────────────────────────────────────────────

class TestMigratedTriggersCompleteness:
    """MIGRATED_TRIGGERS ⊆ proposer_registry trigger_names；proposer trigger_names ⊆ MIGRATED_TRIGGERS。"""

    def test_migrated_triggers_is_frozenset(self):
        from core.scheduler.gating import MIGRATED_TRIGGERS
        assert isinstance(MIGRATED_TRIGGERS, frozenset)
        assert len(MIGRATED_TRIGGERS) > 0

    def test_all_migrated_triggers_have_proposers(self):
        """每个 MIGRATED_TRIGGERS 成员都必须在 proposer_registry 中有至少一个 proposer 覆盖它。"""
        from core.scheduler.gating import MIGRATED_TRIGGERS
        from core.scheduler.proposer_registry import iter_proposers, _reset_for_tests

        # 强制重新加载 builtin proposers
        _reset_for_tests()
        covered: set[str] = set()
        for entry in iter_proposers():
            covered.update(entry.trigger_names)

        uncovered = MIGRATED_TRIGGERS - covered
        assert not uncovered, (
            f"MIGRATED_TRIGGERS 中以下 trigger 没有 proposer: {uncovered}"
        )

    def test_all_proposer_triggers_in_migrated_triggers(self):
        """注册的 proposer trigger_names 都应该在 MIGRATED_TRIGGERS 中。"""
        from core.scheduler.gating import MIGRATED_TRIGGERS
        from core.scheduler.proposer_registry import iter_proposers, _reset_for_tests

        _reset_for_tests()
        extra: set[str] = set()
        for entry in iter_proposers():
            for tname in entry.trigger_names:
                if tname not in MIGRATED_TRIGGERS:
                    extra.add(tname)

        assert not extra, (
            f"以下 proposer trigger 未在 MIGRATED_TRIGGERS 中: {extra}"
        )

    def test_known_speaking_triggers_all_present(self):
        """已知发言 trigger 全部在 MIGRATED_TRIGGERS 中。"""
        from core.scheduler.gating import MIGRATED_TRIGGERS

        required = {
            "morning_greeting", "night_reminder", "random_message", "weather_alert",
            "daily_journal", "spontaneous_recall", "diary_reminder", "diary_share_reminder",
            "period_reminder", "topic_followup", "birthday_midnight", "birthday_eve",
            "birthday_afternoon", "birthday_night", "timenode", "festival", "holiday_boost",
            "hr_critical", "hr_high", "sleep_end", "garden_bloom",
            "garden_harvest_expired", "garden_handle_ask", "garden_handle_gift",
            "garden_handle_self", "garden_vase_wilted", "reminders",
        }
        missing = required - MIGRATED_TRIGGERS
        assert not missing, f"以下发言 trigger 未在 MIGRATED_TRIGGERS: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Legacy speaking _check_* 函数在 live 模式下让路
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacySpeakingTriggersLetPath:
    """Legacy speaking _check_* 在 live 模式（legacy_tick_should_send()=False）下不调用 _pipeline_send。"""

    @pytest.mark.asyncio
    async def test_check_morning_no_send_in_live_mode(self, monkeypatch):
        """_check_morning 在 live 模式不调用 _pipeline_send。"""
        import core.scheduler.triggers.time_based as tb
        import core.scheduler.execution as exec_mod

        calls = []
        monkeypatch.setattr(exec_mod, "EXECUTE_MODE", "live")

        async def fake_send(*a, **kw):
            calls.append(("morning", a, kw))
            return "sent"

        monkeypatch.setattr("core.scheduler.loop._pipeline_send", fake_send)
        await tb._check_morning()
        assert not calls, "_check_morning 在 live 模式不应调用 _pipeline_send"

    @pytest.mark.asyncio
    async def test_check_night_no_send_in_live_mode(self, monkeypatch):
        """_check_night 在 live 模式不调用 _pipeline_send。"""
        import core.scheduler.triggers.time_based as tb
        import core.scheduler.execution as exec_mod

        calls = []
        monkeypatch.setattr(exec_mod, "EXECUTE_MODE", "live")

        async def fake_send(*a, **kw):
            calls.append(kw)
            return "sent"

        monkeypatch.setattr("core.scheduler.loop._pipeline_send", fake_send)
        await tb._check_night()
        assert not calls

    @pytest.mark.asyncio
    async def test_check_period_no_send_in_live_mode(self, monkeypatch):
        """_check_period 在 live 模式不调用 _pipeline_send。"""
        import core.scheduler.triggers.period as period_mod
        import core.scheduler.execution as exec_mod

        calls = []
        monkeypatch.setattr(exec_mod, "EXECUTE_MODE", "live")

        async def fake_send(*a, **kw):
            calls.append(kw)
            return "sent"

        monkeypatch.setattr("core.scheduler.loop._pipeline_send", fake_send)
        await period_mod._check_period()
        assert not calls

    @pytest.mark.asyncio
    async def test_check_reminders_no_send_in_live_mode(self, monkeypatch):
        """loop._check_reminders 在 live 模式不调用 _pipeline_send。"""
        import core.scheduler.loop as loop
        import core.scheduler.execution as exec_mod

        calls = []
        monkeypatch.setattr(exec_mod, "EXECUTE_MODE", "live")

        async def fake_send(*a, **kw):
            calls.append(kw)
            return "sent"

        monkeypatch.setattr(loop, "_pipeline_send", fake_send)
        await loop._check_reminders()
        assert not calls

    def test_legacy_tick_should_send_false_in_live_mode(self):
        """legacy_tick_should_send() 在 EXECUTE_MODE=live 时返回 False。"""
        from core.scheduler.execution import legacy_tick_should_send, EXECUTE_MODE
        assert EXECUTE_MODE == "live"
        assert legacy_tick_should_send() is False

    def test_legacy_tick_should_send_true_with_force(self):
        """legacy_tick_should_send(force=True) 无论 EXECUTE_MODE 返回 True（manual_trigger 用）。"""
        from core.scheduler.execution import legacy_tick_should_send
        assert legacy_tick_should_send(force=True) is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Maintenance tick 不在 MIGRATED_TRIGGERS 中
# ─────────────────────────────────────────────────────────────────────────────

class TestMaintenanceNotInMigratedTriggers:
    """纯维护 trigger 不在 MIGRATED_TRIGGERS 中，不受发言 gating 影响。"""

    def test_pure_maintenance_not_migrated(self):
        from core.scheduler.gating import MIGRATED_TRIGGERS

        pure_maintenance = {
            "episodic_decay", "dlq_monitor", "log_maintenance",
            "episodic_sweep", "hidden_state_decay", "hidden_state_consolidate",
            "diary_inject",
        }
        in_migrated = pure_maintenance & MIGRATED_TRIGGERS
        assert not in_migrated, (
            f"维护型 trigger 不应出现在 MIGRATED_TRIGGERS: {in_migrated}"
        )

    def test_maintenance_triggers_no_pipeline_send(self):
        """episodic_sweep 和 hidden_state_decay 不调用 _pipeline_send（维护型）。"""
        sweep_src = (ROOT / "core/scheduler/triggers/episodic_sweep.py").read_text(encoding="utf-8")
        decay_src = (ROOT / "core/scheduler/triggers/hidden_state_decay.py").read_text(encoding="utf-8")
        assert "_pipeline_send" not in sweep_src
        assert "_pipeline_send" not in decay_src


# ─────────────────────────────────────────────────────────────────────────────
# 5. execute_prompt 只在 sent=True 后 mark
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutePromptMarkSemantics:
    """execute_prompt 只在 _pipeline_send 返回非 None 后调用 _mark。"""

    @pytest.mark.asyncio
    async def test_no_mark_when_pipeline_returns_none(self, monkeypatch):
        from core.scheduler import execution
        import core.scheduler.loop as loop

        marks = []

        async def fail_send(prompt, **kwargs):
            return None

        monkeypatch.setattr(loop, "_pipeline_send", fail_send)
        monkeypatch.setattr(loop, "_mark", lambda name: marks.append(name))

        result = await execution.execute_prompt(
            trigger_name="morning_greeting",
            prompt_factory=lambda: "test",
            dry_run=False,
            would_mark=["morning_greeting"],
        )
        assert result.sent is False
        assert marks == [], "pipeline 返回 None 时不应调用 _mark"

    @pytest.mark.asyncio
    async def test_mark_called_after_successful_send(self, monkeypatch):
        from core.scheduler import execution
        import core.scheduler.loop as loop

        marks = []

        async def success_send(prompt, **kwargs):
            return "reply text"

        monkeypatch.setattr(loop, "_pipeline_send", success_send)
        monkeypatch.setattr(loop, "_mark", lambda name: marks.append(name))

        result = await execution.execute_prompt(
            trigger_name="morning_greeting",
            prompt_factory=lambda: "test",
            dry_run=False,
            would_mark=["morning_greeting"],
        )
        assert result.sent is True
        assert "morning_greeting" in marks

    @pytest.mark.asyncio
    async def test_after_send_not_called_when_blocked(self, monkeypatch):
        """after_send 回调在 pipeline 返回 None 时不调用。"""
        from core.scheduler import execution
        import core.scheduler.loop as loop

        after_calls = []

        async def fail_send(prompt, **kwargs):
            return None

        monkeypatch.setattr(loop, "_pipeline_send", fail_send)

        result = await execution.execute_prompt(
            trigger_name="reminders",
            prompt_factory=lambda: "test",
            dry_run=False,
            would_mark=[],
            after_send=lambda: after_calls.append(True),
        )
        assert result.sent is False
        assert after_calls == [], "after_send 不应在 pipeline 返回 None 时调用"


# ─────────────────────────────────────────────────────────────────────────────
# 6. gating._decide 是发言决策唯一权威
# ─────────────────────────────────────────────────────────────────────────────

class TestGatingIsAuthority:
    """gating._decide 做所有 active-window / DND 决策；_pipeline_send 不重复过滤。"""

    def test_active_window_decision_in_gating_not_pipeline_send(self):
        """active-window 过滤代码在 gating.py 而非 loop._pipeline_send 的函数体中。"""
        import core.scheduler.loop as loop
        import core.scheduler.gating as gating

        pipeline_src = inspect.getsource(loop._pipeline_send)
        gating_src = inspect.getsource(gating._decide)

        # _pipeline_send 不包含 active_window_behavior 决策
        assert "active_window_behavior" not in pipeline_src, (
            "_pipeline_send 不应包含 active_window_behavior 决策"
        )
        # gating._decide 包含 active_window_behavior 决策
        assert "active_window_behavior" in gating_src

    def test_dnd_decision_in_gating_not_pipeline_send(self):
        """DND 过滤代码在 gating.py 而非 loop._pipeline_send 的函数体中。"""
        import core.scheduler.loop as loop
        import core.scheduler.gating as gating

        pipeline_src = inspect.getsource(loop._pipeline_send)
        gating_src = inspect.getsource(gating._decide)

        assert "is_dnd" not in pipeline_src, (
            "_pipeline_send 不应包含 is_dnd 检查"
        )
        assert "dnd_active" in gating_src

    def test_gating_blocks_filler_when_user_active(self, monkeypatch):
        """gating._decide 在用户活跃时阻止 filler trigger。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=True, dnd_active=False)
        proposals = [_make_proposal("random_message")]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is None
        assert reason == "active_window_filtered"

    def test_gating_blocks_normal_trigger_when_dnd(self, monkeypatch):
        """gating._decide 在 DND 时阻止普通 trigger。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=False, dnd_active=True)
        proposals = [_make_proposal("morning_greeting")]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is None
        assert reason == "dnd_filtered"

    def test_gating_allows_exempt_when_user_active(self, monkeypatch):
        """gating._decide 在用户活跃时允许 exempt trigger（hr_critical）。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=True, dnd_active=False)
        proposals = [_make_proposal("hr_critical", urgency=1.0)]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is not None
        assert picked.trigger_name == "hr_critical"

    def test_gating_allows_emergency_when_dnd(self, monkeypatch):
        """gating._decide 在 DND 时允许 emergency trigger（hr_critical）。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=False, dnd_active=True)
        proposals = [_make_proposal("hr_critical", urgency=1.0)]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is not None
        assert picked.trigger_name == "hr_critical"


# ─────────────────────────────────────────────────────────────────────────────
# 7. 发言 trigger 进入 proposer 候选流、不绕过 gating
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeakingTriggerProposerPath:
    """发言 trigger 通过 proposer 注册并由 gating 仲裁，不直接调用 _pipeline_send。"""

    def test_all_known_speaking_triggers_have_registered_proposers(self):
        """每个已知发言 trigger 都有对应的 proposer fn 注册。"""
        from core.scheduler.proposer_registry import iter_proposers, _reset_for_tests

        _reset_for_tests()
        covered: set[str] = set()
        for entry in iter_proposers():
            covered.update(entry.trigger_names)

        known_speaking = {
            "morning_greeting", "night_reminder", "random_message", "weather_alert",
            "daily_journal", "spontaneous_recall", "diary_reminder", "diary_share_reminder",
            "period_reminder", "topic_followup", "birthday_midnight", "birthday_eve",
            "birthday_afternoon", "birthday_night", "timenode", "festival", "holiday_boost",
            "hr_critical", "hr_high", "sleep_end", "garden_bloom",
            "garden_harvest_expired", "garden_handle_ask", "garden_handle_gift",
            "garden_handle_self", "garden_vase_wilted", "reminders",
        }
        uncovered = known_speaking - covered
        assert not uncovered, f"以下发言 trigger 没有 proposer: {uncovered}"

    def test_legacy_check_topic_followup_is_noop(self):
        """_check_topic_followup 是已标记为 legacy no-op 的存根。"""
        import core.scheduler.triggers.memory as memory_mod
        src = inspect.getsource(memory_mod._check_topic_followup)
        # should be a no-op that logs/returns without calling _pipeline_send
        assert "_pipeline_send" not in src

    def test_proposer_registry_loads_all_builtin_modules(self):
        """proposer_registry._ensure_builtins_loaded 覆盖所有 trigger 模块。"""
        from core.scheduler.proposer_registry import iter_proposers, _reset_for_tests
        _reset_for_tests()
        proposers = iter_proposers()
        assert len(proposers) >= 15, (
            f"proposer 数量过少 ({len(proposers)})，可能有模块未加载"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 8. gating 阻止的 trigger 不 mark
# ─────────────────────────────────────────────────────────────────────────────

class TestGatingBlockedNotMarked:
    """当 gating 阻止 trigger 时，execute 函数不被调用，_mark 不被调用。"""

    @pytest.mark.asyncio
    async def test_gating_blocked_execute_never_called(self, monkeypatch):
        """gating 返回 None 时，execute 函数不会被调用。"""
        from core.scheduler.gating import _decide
        from core.scheduler.state_machine import TriggerState

        _patch_gating_env(monkeypatch, user_active=True, dnd_active=False)

        execute_called = []

        async def fake_execute(*, dry_run: bool):
            execute_called.append(dry_run)
            from core.scheduler.execution import ExecuteResult
            return ExecuteResult(trigger_name="random_message", would_send_prompt="", sent=False, dry_run=dry_run)

        from core.scheduler.gating import TriggerProposal

        proposal = TriggerProposal(
            trigger_name="random_message",
            urgency=0.8,
            topic_source="test",
            requires_state=[TriggerState.QUIET],
            execute=fake_execute,
        )
        picked, reason, _ = _decide("u1", [proposal])
        assert picked is None
        assert reason == "active_window_filtered"
        assert execute_called == [], "gating 返回 None 时 execute 不应被调用"


# ─────────────────────────────────────────────────────────────────────────────
# 9. high-priority/exempt 语义通过 gating 保持
# ─────────────────────────────────────────────────────────────────────────────

class TestHighPriorityExemptSemantics:
    """高优先级/exempt trigger 在用户活跃或 DND 时仍通过 gating。"""

    def test_high_priority_triggers_all_exempt_in_policy(self):
        """_HIGH_PRIORITY_TRIGGERS 集合与 POLICY_TABLE exempt 集对齐。"""
        from core.scheduler.policy import POLICY_TABLE
        from core.scheduler.loop import _HIGH_PRIORITY_TRIGGERS

        policy_exempt = {
            tid for tid, p in POLICY_TABLE.items()
            if p.active_window_behavior == "exempt"
        }
        assert policy_exempt == _HIGH_PRIORITY_TRIGGERS, (
            f"POLICY_TABLE exempt 集与 _HIGH_PRIORITY_TRIGGERS 不一致: "
            f"policy={policy_exempt}, const={_HIGH_PRIORITY_TRIGGERS}"
        )

    def test_birthday_series_all_exempt(self, monkeypatch):
        """生日四档 trigger 在用户活跃时通过 gating（exempt）。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=True, dnd_active=False)

        for tname in ("birthday_midnight", "birthday_eve", "birthday_afternoon", "birthday_night"):
            proposals = [_make_proposal(tname, urgency=0.9)]
            picked, reason, _ = _decide("u1", proposals)
            assert picked is not None, f"{tname} 在用户活跃时应通过 gating"
            assert picked.trigger_name == tname

    def test_period_reminder_exempt(self, monkeypatch):
        """period_reminder 在用户活跃时通过 gating（exempt）。"""
        from core.scheduler.gating import _decide

        _patch_gating_env(monkeypatch, user_active=True, dnd_active=False)
        proposals = [_make_proposal("period_reminder", urgency=0.7)]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is not None
        assert picked.trigger_name == "period_reminder"

    def test_hr_critical_passes_both_active_and_dnd(self, monkeypatch):
        """hr_critical 在用户活跃+DND 时仍通过 gating。"""
        from core.scheduler.gating import _decide

        # user active + DND both on
        _patch_gating_env(monkeypatch, user_active=True, dnd_active=True)
        proposals = [_make_proposal("hr_critical", urgency=1.0)]
        picked, reason, _ = _decide("u1", proposals)
        assert picked is not None
        assert picked.trigger_name == "hr_critical"


# ─────────────────────────────────────────────────────────────────────────────
# 10. 剩余 R2-D 待办结构验证
# ─────────────────────────────────────────────────────────────────────────────

class TestR2DRemainingStructure:
    """验证 R2-D 依赖的结构已就绪（defer 队列入口、DND 接线）。"""

    def test_policy_table_has_defer_entries(self):
        """POLICY_TABLE 中 defer 条目已有 max_defer_age_secs 字段（R2-D defer 队列用）。"""
        from core.scheduler.policy import POLICY_TABLE

        defer_triggers = [
            t for t, p in POLICY_TABLE.items()
            if p.active_window_behavior == "defer"
        ]
        assert len(defer_triggers) > 0, "POLICY_TABLE 没有 defer 条目"
        for tname in defer_triggers:
            p = POLICY_TABLE[tname]
            assert p.max_defer_age_secs > 0, (
                f"{tname} 有 defer 但 max_defer_age_secs=0"
            )

    def test_dnd_detect_and_set_exists(self):
        """dnd.detect_and_set 已实现（R2-D 接线 main.py 用）。"""
        from core.scheduler.triggers import dnd
        assert hasattr(dnd, "detect_and_set"), (
            "dnd.detect_and_set 不存在 — R2-D 接入 main.py 需要它"
        )
        assert hasattr(dnd, "is_dnd"), "dnd.is_dnd 不存在"

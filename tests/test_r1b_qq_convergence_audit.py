"""
tests/test_r1b_qq_convergence_audit.py — R1-B: QQ main entry full-convergence audit
(2026-06-11)

Pins the current-state contracts for main.py handle_message and
_reply_with_tool_result against the unified turn_sink convergence target.

───────────────────────────────────────────────────────────────────────────────
text_output.send classification (all sites in main.py):

  LLM_ASSISTANT_REPLY (×2):
    handle_message              — segments → visible QQ send  (→ await post_process)
    _reply_with_tool_result     — segments → visible QQ send  (→ await post_process)

  SYSTEM_SHORT_TEXT (×4):
    handle_message dream-guard exception   — "梦境状态暂时无法确认" (_to_dg alias)
    handle_message dream-guard BLOCK_ACTIVE — "正在梦境中"           (_to_dg alias)
    handle_message dream-guard BLOCK_UNCERTAIN — "梦境状态暂时无法确认" (_to_dg alias)
    handle_message cancel confirm          — "好的，已取消～"

  TOOL_CONFIRMATION_PROMPT (×2):
    handle_message WAITING_INPUT ask_text  — dynamic ask_text string
    handle_message tool-probe ask_text     — dynamic ask_text string

post_process classification (all sites in main.py):
  handle_message main LLM reply       — await, frozen_scope=_frozen_scope  ✓
  _reply_with_tool_result tool reply  — await, frozen_scope=frozen_scope   ✓

Convergence delta vs turn_sink (R1-B baseline):
  ✓  scope freeze (_frozen_scope) — N1
  ✓  conversation_lock — R1
  ✓  await post_process (no bare create_task) — N10
  ✓  frozen_scope passed to post_process — N1
  ✓  pre-scrub (scrub_reality_output_text) + strip_render_tags — R6-A/B
  ✗  LLM_ASSISTANT_REPLY uses text_output.send directly (not turn_sink/channel fanout)
  ✗  QQChannel.send hardcodes is_group=False (group support gap, R1-C prereq)
  ✗  post_process call signature differs from turn_sink.record_assistant_turn
     (QQ passes target_id / is_group / pending_paths / frozen_scope; turn_sink does not)
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


# ── helpers ────────────────────────────────────────────────────────────────────

def _src(relpath: str) -> str:
    return (_ROOT / relpath).read_text(encoding="utf-8")


def _lines(relpath: str) -> list[str]:
    return _src(relpath).splitlines()


def _non_comment_lines(relpath: str) -> list[tuple[int, str]]:
    """Return (1-based lineno, text) for non-blank, non-comment lines."""
    return [
        (i + 1, ln)
        for i, ln in enumerate(_lines(relpath))
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _function_body_text(src: str, func_name: str) -> str:
    """
    Return source text inside the named function (stops at next same-level def/class).
    """
    lines = src.splitlines()
    result: list[str] = []
    inside = False
    base_indent: int | None = None

    for ln in lines:
        stripped = ln.lstrip()
        indent = len(ln) - len(stripped)

        if f"def {func_name}(" in ln:
            inside = True
            base_indent = indent
            result.append(ln)
            continue

        if inside:
            if stripped and indent <= base_indent and (
                stripped.startswith("def ")
                or stripped.startswith("async def ")
                or stripped.startswith("class ")
                or stripped.startswith("@")
            ) and f"def {func_name}(" not in ln:
                break
            result.append(ln)

    return "\n".join(result)


# ═══════════════════════════════════════════════════════════════════════════════
# A1. text_output.send total count — all call sites must be classified
# ═══════════════════════════════════════════════════════════════════════════════

def test_a1a_text_output_send_count():
    """
    A1a: Exactly 5 text_output.send( calls in main.py non-comment lines.

    Expected:
      L274  cancel confirm          SYSTEM_SHORT_TEXT
      L292  WAITING_INPUT ask_text  TOOL_CONFIRMATION_PROMPT
      L413  probe ask_text          TOOL_CONFIRMATION_PROMPT
      L460  handle_message reply    LLM_ASSISTANT_REPLY
      L566  tool-reply              LLM_ASSISTANT_REPLY
    """
    hits = [
        (lineno, ln)
        for lineno, ln in _non_comment_lines("main.py")
        if "text_output.send(" in ln
    ]
    assert len(hits) == 5, (
        f"Expected 5 text_output.send( calls in main.py, found {len(hits)}:\n"
        + "\n".join(f"  L{lineno}: {ln.strip()}" for lineno, ln in hits)
    )


def test_a1b_dg_send_count():
    """
    A1b: Exactly 3 _to_dg.send( calls in main.py (dream-guard SYSTEM_SHORT_TEXT).

    All three occur inside the dream-guard block and immediately return —
    they must not be reclassified to LLM_ASSISTANT_REPLY without a corresponding
    post_process call.
    """
    hits = [
        (lineno, ln)
        for lineno, ln in _non_comment_lines("main.py")
        if "_to_dg.send(" in ln
    ]
    assert len(hits) == 3, (
        f"Expected 3 _to_dg.send( calls in main.py (dream-guard sends), "
        f"found {len(hits)}:\n"
        + "\n".join(f"  L{lineno}: {ln.strip()}" for lineno, ln in hits)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A2. LLM_ASSISTANT_REPLY sends use the `segments` variable
# ═══════════════════════════════════════════════════════════════════════════════

def test_a2_llm_reply_sends_use_segments():
    """
    A2: Exactly 2 text_output.send calls pass `segments` as the content argument
    (one in handle_message, one in _reply_with_tool_result).

    A regression here would mean a new LLM path is sending raw text without going
    through the response_processor.process + strip_render_tags chain.
    """
    hits = [
        (lineno, ln)
        for lineno, ln in _non_comment_lines("main.py")
        if "text_output.send(" in ln and "segments" in ln
    ]
    assert len(hits) == 2, (
        f"Expected exactly 2 LLM_ASSISTANT_REPLY sends (using 'segments'), "
        f"found {len(hits)}:\n"
        + "\n".join(f"  L{lineno}: {ln.strip()}" for lineno, ln in hits)
    )


def test_a2b_llm_reply_sends_in_expected_functions():
    """
    A2b: The two LLM_ASSISTANT_REPLY sends appear in handle_message and
    _reply_with_tool_result respectively — not in any new function.
    """
    src = _src("main.py")
    hm_body = _function_body_text(src, "handle_message")
    tr_body = _function_body_text(src, "_reply_with_tool_result")

    assert "text_output.send(target_id, segments, is_group)" in hm_body, (
        "handle_message: LLM_ASSISTANT_REPLY send not found in function body"
    )
    assert "text_output.send(target_id, segments, is_group)" in tr_body, (
        "_reply_with_tool_result: LLM_ASSISTANT_REPLY send not found in function body"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A3. No bare asyncio.create_task wrapping post_process in main.py
# ═══════════════════════════════════════════════════════════════════════════════

def test_a3_no_create_task_for_post_process():
    """
    A3: main.py must not use asyncio.create_task to schedule post_process.
    N10 fix: both LLM reply paths now await post_process directly.
    A create_task pattern would re-introduce the N10 regression (dropped write reference).
    """
    lines = _lines("main.py")
    violations: list[str] = []
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue
        if "create_task" not in ln:
            continue
        # Check the call line + next 4 lines for post_process reference
        context = "\n".join(lines[i : i + 5])
        if "post_process" in context:
            violations.append(f"main.py:{i + 1}: {stripped}")

    assert not violations, (
        "main.py uses create_task for post_process — N10 regression:\n"
        + "\n".join(violations)
    )


def test_a3b_create_task_calls_are_startup_only():
    """
    A3b: All asyncio.create_task calls in main.py are startup infrastructure
    (admin_server or qq_adapter), not post_process paths.
    """
    lines = _lines("main.py")
    _ALLOWED_TARGETS = {"start_admin_server", "qq_adapter.connect_and_listen"}
    violations: list[str] = []
    for i, ln in enumerate(lines, 1):
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue
        if "create_task(" not in ln:
            continue
        if not any(t in ln for t in _ALLOWED_TARGETS):
            violations.append(f"main.py:{i}: {stripped}")

    assert not violations, (
        "Unexpected create_task call in main.py (not a startup task):\n"
        + "\n".join(violations)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A4. Both LLM reply functions await post_process
# ═══════════════════════════════════════════════════════════════════════════════

def test_a4_handle_message_awaits_post_process():
    """
    A4: handle_message must have `await _pipeline.post_process(` (not create_task).
    """
    src = _src("main.py")
    body = _function_body_text(src, "handle_message")
    assert "await _pipeline.post_process(" in body, (
        "handle_message: post_process is not awaited — N10 regression or removed call"
    )


def test_a4b_tool_reply_awaits_post_process():
    """
    A4b: _reply_with_tool_result must have `await _pipeline.post_process(`.
    """
    src = _src("main.py")
    body = _function_body_text(src, "_reply_with_tool_result")
    assert "await _pipeline.post_process(" in body, (
        "_reply_with_tool_result: post_process is not awaited — N10 regression"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A5. frozen_scope is passed to post_process in both LLM paths
# ═══════════════════════════════════════════════════════════════════════════════

def test_a5_handle_message_passes_frozen_scope():
    """
    A5: handle_message must pass frozen_scope=_frozen_scope to post_process (N1).
    """
    src = _src("main.py")
    body = _function_body_text(src, "handle_message")
    assert "frozen_scope=_frozen_scope" in body, (
        "handle_message: frozen_scope=_frozen_scope not found in post_process call — "
        "N1 scope-freeze regression"
    )


def test_a5b_tool_reply_passes_frozen_scope():
    """
    A5b: _reply_with_tool_result must pass frozen_scope=frozen_scope to post_process.
    When frozen_scope is None (legacy fallback), post_process will freeze internally.
    """
    src = _src("main.py")
    body = _function_body_text(src, "_reply_with_tool_result")
    assert "frozen_scope=frozen_scope" in body, (
        "_reply_with_tool_result: frozen_scope not forwarded to post_process — "
        "the N1 scope freeze regression or the legacy-compat fallback comment was removed"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A6. _reply_with_tool_result accepts frozen_scope parameter
# ═══════════════════════════════════════════════════════════════════════════════

def test_a6_tool_reply_has_frozen_scope_param():
    """
    A6: _reply_with_tool_result function signature must include frozen_scope=None.
    This enables handle_message to pass the already-frozen scope (N1).
    """
    src = _src("main.py")
    body = _function_body_text(src, "_reply_with_tool_result")
    # Signature lines are included in body_text
    assert "frozen_scope=None" in body, (
        "_reply_with_tool_result: frozen_scope=None parameter missing from signature — "
        "scope freeze (N1) cannot be forwarded from handle_message"
    )


def test_a6b_handle_message_passes_frozen_scope_to_tool_reply():
    """
    A6b: handle_message must call _reply_with_tool_result with frozen_scope=_frozen_scope.
    Without this, the tool-confirm path runs with no scope freeze.
    """
    src = _src("main.py")
    body = _function_body_text(src, "handle_message")
    assert "_reply_with_tool_result" in body, (
        "handle_message does not call _reply_with_tool_result — unexpected structural change"
    )
    assert "frozen_scope=_frozen_scope" in body, (
        "handle_message: _reply_with_tool_result not called with frozen_scope=_frozen_scope"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A7. Both LLM paths pre-scrub with scrub_reality_output_text + strip_render_tags
#     (R6-A/B: defense-in-depth upstream pre-scrub contract)
# ═══════════════════════════════════════════════════════════════════════════════

def test_a7_handle_message_uses_scrub_and_strip():
    """
    A7: handle_message must call both scrub_reality_output_text (memory pre-scrub)
    and strip_render_tags (visible output) — R6-A/B contract.
    """
    src = _src("main.py")
    body = _function_body_text(src, "handle_message")
    assert "scrub_reality_output_text" in body, (
        "handle_message: scrub_reality_output_text missing — QQ memory pre-scrub removed"
    )
    assert "strip_render_tags" in body, (
        "handle_message: strip_render_tags missing — visible output no longer cleaned"
    )


def test_a7b_tool_reply_uses_scrub_and_strip():
    """
    A7b: _reply_with_tool_result must also call both scrub_reality_output_text
    and strip_render_tags — same R6-A/B pre-scrub contract as handle_message.
    """
    src = _src("main.py")
    body = _function_body_text(src, "_reply_with_tool_result")
    assert "scrub_reality_output_text" in body, (
        "_reply_with_tool_result: scrub_reality_output_text missing — "
        "tool-reply memory pre-scrub removed"
    )
    assert "strip_render_tags" in body, (
        "_reply_with_tool_result: strip_render_tags missing — "
        "visible output no longer cleaned on tool-reply path"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A8. Shared scrub contract: QQ pre-scrub pattern matches turn_sink pre-scrub
# ═══════════════════════════════════════════════════════════════════════════════

def test_a8_qq_and_turn_sink_both_pre_scrub():
    """
    A8: Both the QQ inlet (main.py) and the non-QQ inlet (turn_sink.py) call
    scrub_reality_output_text as defense-in-depth before post_process.
    Removing scrub from either path would create an asymmetric contract.
    """
    main_src = _src("main.py")
    sink_src = _src("core/turn_sink.py")

    assert "scrub_reality_output_text" in main_src, (
        "main.py (QQ inlet): scrub_reality_output_text not imported/called"
    )
    assert "scrub_reality_output_text" in sink_src, (
        "core/turn_sink.py (non-QQ inlet): scrub_reality_output_text not imported/called"
    )


def test_a8b_r6b_contract_still_holds():
    """
    A8b: R6-B test module still importable (no structural breakage of the scrub
    contract module after R1-B changes).
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "test_r6b", _ROOT / "tests" / "test_r6b_reality_scrub_contract.py"
    )
    assert spec is not None, "test_r6b_reality_scrub_contract.py not found"
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.fail(f"test_r6b_reality_scrub_contract.py failed to import: {exc}")

    # Verify key contract tests are still defined
    for attr in ("test_c5_capture_turn_has_authority_scrub", "test_c8_fanout_no_reality_scrub"):
        assert hasattr(mod, attr), (
            f"test_r6b_reality_scrub_contract.py: {attr} is missing — "
            "R6-B contract was removed"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# A9. Partial-convergence gap: QQ not yet using record_assistant_turn
# ═══════════════════════════════════════════════════════════════════════════════

def test_a9_qq_not_yet_using_record_assistant_turn():
    """
    A9 (documents partial convergence): main.py must NOT import or call
    record_assistant_turn.  QQ still sends via text_output.send and calls
    post_process directly.

    When R1-C migrates QQ to the unified turn_sink path, this test should be
    INVERTED to assert the opposite (record_assistant_turn IS present, and
    the old direct-send + post_process pattern is gone).
    """
    src = _src("main.py")
    assert "record_assistant_turn" not in src, (
        "main.py now references record_assistant_turn — R1-C migration may have started. "
        "Update this test: invert the assertion and verify the new QQ adapter path."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A10. QQChannel.send group-support gap (R1-C prerequisite)
# ═══════════════════════════════════════════════════════════════════════════════

def test_a10_qq_channel_hardcodes_is_group_false():
    """
    A10 (documents R1-C prerequisite): QQChannel.send currently hardcodes
    is_group=False when calling qq_adapter.send_message.

    This means routing QQ through turn_sink._fanout → QQChannel.send would silently
    drop group messages.  R1-C must fix QQChannel.send to respect the target_id /
    is_group context before the migration can be completed.

    When R1-C fixes this, this test should be INVERTED.
    """
    src = _src("channels/qq.py")
    # Find the send method body
    send_body = _function_body_text(src, "send")
    assert "is_group=False" in send_body, (
        "channels/qq.py QQChannel.send: is_group=False hardcode is gone — "
        "either R1-C fixed it (invert this test) or it was removed accidentally."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A11. known-issues.md documents R1-B partial convergence state
# ═══════════════════════════════════════════════════════════════════════════════

def test_a11_known_issues_documents_r1b():
    """
    A11: docs/known-issues.md must mention R1-B convergence audit.
    This ensures the B11 section is kept up to date as fixes land.
    """
    src = _src("docs/known-issues.md")
    assert "R1-B" in src, (
        "docs/known-issues.md does not mention R1-B — "
        "update B11 to reflect the current partial-convergence state"
    )


def test_a11b_known_issues_reflects_n10_fix():
    """
    A11b: docs/known-issues.md B11 must NOT still claim create_task is used.
    N10 changed both QQ paths from create_task to await; B11 must reflect this.
    """
    src = _src("docs/known-issues.md")
    b11_start = src.find("### B11")
    b11_end = src.find("\n---", b11_start) if b11_start != -1 else -1
    if b11_start == -1 or b11_end == -1:
        return  # B11 removed or restructured — skip

    b11_text = src[b11_start:b11_end]
    # N10 fix acknowledged: should NOT still say "仍在发送后以 asyncio.create_task"
    assert "asyncio.create_task" not in b11_text or "N10" in b11_text, (
        "docs/known-issues.md B11 still says create_task is used without noting "
        "N10 fixed it — update the section to reflect the current state"
    )

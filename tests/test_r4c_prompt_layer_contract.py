"""
tests/test_r4c_prompt_layer_contract.py
========================================
Fable R4-C: PromptLayer / drop_priority 门禁强化

Long-term contracts to prevent regressions after R4-A/R4-B.

Rule 1 — _DROPPABLE central list must NOT appear in core/prompt_builder.py.
Rule 2 — All 8 known droppable layers declare their _drop_priority in source.
Rule 3 — Keyword gate: any _layer whose name contains a "droppable keyword"
          must either declare _drop_priority (in the same messages.append block)
          or appear in NON_DROPPABLE_ALLOWLIST with a justification.
Rule 4 — _drop_priority must be an integer literal (never a string, never "30").
Rule 5 — Same _drop_priority value is explicitly permitted (batch semantics).
Rule 6 — PromptLayer→message conversion contract: None→no key; int→key; name→_layer.
          sanitize_messages() strips all underscore-prefixed keys before LLM calls.
"""
from __future__ import annotations

import inspect
import re

import pytest

# ---------------------------------------------------------------------------
# Shared constants used by multiple test classes
# ---------------------------------------------------------------------------

# All 8 currently declared droppable layers and their expected _drop_priority values.
# "Lower value = dropped first" — do not change a priority without updating this table.
DROPPABLE_LAYER_PRIORITIES: dict[str, int] = {
    "dream_afterglow_soft_hint": 10,
    "6g_dream_impression":       20,
    "6b_event_search":           30,
    "mid_term":                  40,
    "6d_diary_context":          50,
    "6e_inner_diary":            60,
    "6c_episodic":               70,
    "5.5_lore":                  80,
}

# Keywords that signal "this layer is likely droppable".
# Any _layer value whose name contains at least one of these must either declare
# _drop_priority in the same append block, or appear in NON_DROPPABLE_ALLOWLIST.
DROPPABLE_KEYWORDS: frozenset[str] = frozenset({
    "dream",
    "diary",
    "episodic",
    "event",
    "lore",
    "afterglow",
    "impression",
    "mid_term",
})

# Layers that match a keyword but are intentionally NOT auto-droppable.
# Key = exact _layer value; Value = human-readable justification (≥20 chars).
# To exempt a future layer: add it here, do NOT add _drop_priority.
NON_DROPPABLE_ALLOWLIST: dict[str, str] = {
    "9.5_episodic_top": (
        "Single top memory placed *after* history for recency attention benefit. "
        "Its positioning (right before user message) is the entire point; "
        "auto-dropping it defeats the sweet-spot attention design. "
        "Small footprint (one line); no meaningful token saving from dropping it."
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_pb_source() -> str:
    import core.prompt_builder as pb
    return inspect.getsource(pb)


def _extract_layers_from_source(src: str) -> list[tuple[str, int | None]]:
    """
    Scan prompt_builder source for messages.append({…}) blocks that declare _layer.

    For each such block return (layer_name, drop_priority | None).
    Only inspects the first 700 characters of each append block, which is
    sufficient to cover any _drop_priority that follows _layer in the same dict.

    Approach: split on 'messages.append(' to isolate each append call, then
    regex-search within each fragment.  This avoids cross-block contamination.
    """
    layer_re = re.compile(r'"_layer":\s*"([^"]+)"')
    prio_re  = re.compile(r'"_drop_priority":\s*(\d+)')

    blocks = src.split("messages.append(")
    results: list[tuple[str, int | None]] = []
    for block in blocks[1:]:
        window = block[:700]
        lm = layer_re.search(window)
        if not lm:
            continue
        layer_name = lm.group(1)
        pm = prio_re.search(window)
        priority = int(pm.group(1)) if pm else None
        results.append((layer_name, priority))
    return results


def _layer_priority_map(src: str) -> dict[str, int | None]:
    """
    Deduplicated {layer_name: drop_priority} from source.
    First occurrence wins (handles fallback paths that reuse the same _layer name).
    """
    result: dict[str, int | None] = {}
    for name, prio in _extract_layers_from_source(src):
        if name not in result:
            result[name] = prio
    return result


def _matches_keyword(layer_name: str) -> bool:
    """Return True if layer_name contains at least one DROPPABLE_KEYWORDS entry."""
    low = layer_name.lower()
    return any(kw in low for kw in DROPPABLE_KEYWORDS)


# ---------------------------------------------------------------------------
# Rule 1 — No _DROPPABLE central list in core/prompt_builder.py
# ---------------------------------------------------------------------------

class TestNoDROPPABLEInSource:
    """
    _DROPPABLE was retired in R4-B.  It must never be re-introduced in the
    production trimmer.  (It may still exist in test files or comments.)
    """

    def test_droppable_constant_absent_from_prompt_builder(self):
        src = _get_pb_source()
        assert "_DROPPABLE" not in src, (
            "_DROPPABLE central list was re-introduced in core/prompt_builder.py. "
            "R4-B retired it; all trimming must use per-message _drop_priority."
        )

    def test_no_droppable_assignment_in_prompt_builder(self):
        """Confirm no '_DROPPABLE = [...]' or '_DROPPABLE = {' style definition."""
        src = _get_pb_source()
        # A stricter regex that would catch assignment forms
        matches = re.findall(r'\b_DROPPABLE\b', src)
        assert not matches, (
            f"Found {len(matches)} occurrence(s) of _DROPPABLE in prompt_builder source."
        )


# ---------------------------------------------------------------------------
# Rule 2 — All 8 known droppable layers declare _drop_priority
# ---------------------------------------------------------------------------

class TestKnownDroppableLayersHavePriority:
    """
    Verifies that every layer in DROPPABLE_LAYER_PRIORITIES is present in the
    prompt_builder source and carries the expected _drop_priority value.
    """

    def _get_lpm(self) -> dict[str, int | None]:
        return _layer_priority_map(_get_pb_source())

    @pytest.mark.parametrize("layer,expected_prio", DROPPABLE_LAYER_PRIORITIES.items())
    def test_layer_has_expected_priority(self, layer: str, expected_prio: int):
        lpm = self._get_lpm()
        assert layer in lpm, (
            f"Layer {layer!r} not found in any messages.append() block "
            "in core/prompt_builder.py."
        )
        actual = lpm[layer]
        assert actual == expected_prio, (
            f"Layer {layer!r}: expected _drop_priority={expected_prio}, got {actual!r}. "
            "Update DROPPABLE_LAYER_PRIORITIES in this test file if the priority was "
            "intentionally changed."
        )

    def test_complete_droppable_set_size(self):
        """Sentinel: DROPPABLE_LAYER_PRIORITIES must list exactly 8 layers."""
        assert len(DROPPABLE_LAYER_PRIORITIES) == 8, (
            "DROPPABLE_LAYER_PRIORITIES has unexpected size. "
            "Update it when adding or removing a droppable layer."
        )

    def test_all_8_layers_found_in_source(self):
        """All 8 entries must actually appear in prompt_builder source."""
        lpm = self._get_lpm()
        missing = [l for l in DROPPABLE_LAYER_PRIORITIES if l not in lpm]
        assert not missing, f"Layers missing from source: {missing}"


# ---------------------------------------------------------------------------
# Rule 3 — Keyword gate for future layers
# ---------------------------------------------------------------------------

class TestKeywordGate:
    """
    Any _layer whose name matches a DROPPABLE_KEYWORDS entry must either:
      (a) carry _drop_priority in the same append block, or
      (b) appear in NON_DROPPABLE_ALLOWLIST with a justification.

    This catches future layers like 'dream_new_hint' that forget to declare
    a priority.
    """

    def _keyword_layers(self) -> list[tuple[str, int | None]]:
        src = _get_pb_source()
        seen: set[str] = set()
        result = []
        for name, prio in _extract_layers_from_source(src):
            if _matches_keyword(name) and name not in seen:
                seen.add(name)
                result.append((name, prio))
        return result

    def test_all_keyword_layers_have_priority_or_allowlist(self):
        violations: list[str] = []
        for name, prio in self._keyword_layers():
            if prio is None and name not in NON_DROPPABLE_ALLOWLIST:
                violations.append(name)
        assert not violations, (
            "The following layers match droppable keywords but declare neither "
            "_drop_priority nor a NON_DROPPABLE_ALLOWLIST entry:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nFix: either add `\"_drop_priority\": N` to the messages.append() "
            "call, or add the layer to NON_DROPPABLE_ALLOWLIST in this test file "
            "with a justification string."
        )

    def test_allowlist_entries_have_non_trivial_justification(self):
        for name, reason in NON_DROPPABLE_ALLOWLIST.items():
            assert isinstance(reason, str) and len(reason.strip()) >= 20, (
                f"NON_DROPPABLE_ALLOWLIST[{name!r}] justification is too short. "
                "Write at least 20 characters explaining why it is not auto-droppable."
            )

    def test_allowlist_entries_actually_match_keyword(self):
        """Every NON_DROPPABLE_ALLOWLIST key must itself match a droppable keyword."""
        for name in NON_DROPPABLE_ALLOWLIST:
            assert _matches_keyword(name), (
                f"NON_DROPPABLE_ALLOWLIST[{name!r}] does not match any keyword in "
                f"DROPPABLE_KEYWORDS {sorted(DROPPABLE_KEYWORDS)}. "
                "Remove it — this allowlist is only for keyword-matching layers."
            )

    def test_no_layer_in_both_droppable_and_allowlist(self):
        """A layer cannot be both droppable (has priority) and non-droppable (allowlist)."""
        overlap = set(DROPPABLE_LAYER_PRIORITIES) & set(NON_DROPPABLE_ALLOWLIST)
        assert not overlap, (
            f"Layers appear in both DROPPABLE_LAYER_PRIORITIES and "
            f"NON_DROPPABLE_ALLOWLIST: {overlap}. "
            "A layer cannot be both auto-droppable and exempted."
        )

    @pytest.mark.parametrize("layer", list(DROPPABLE_LAYER_PRIORITIES.keys()))
    def test_known_droppable_layer_matches_keyword(self, layer: str):
        """
        Every known droppable layer's name must match at least one keyword,
        confirming the keyword scanner would have flagged it if it were new.
        """
        assert _matches_keyword(layer), (
            f"Layer {layer!r} is in DROPPABLE_LAYER_PRIORITIES but does NOT match "
            f"any keyword in DROPPABLE_KEYWORDS {sorted(DROPPABLE_KEYWORDS)}. "
            "Either add a keyword that covers it, or reconsider its classification."
        )

    def test_keyword_scanner_finds_all_known_droppable_layers(self):
        """
        The keyword scanner must detect all 8 known droppable layers
        (i.e., they all carry their priority in source).
        """
        src = _get_pb_source()
        lpm = _layer_priority_map(src)
        missing_or_no_prio = [
            layer for layer in DROPPABLE_LAYER_PRIORITIES
            if lpm.get(layer) != DROPPABLE_LAYER_PRIORITIES[layer]
        ]
        assert not missing_or_no_prio, (
            f"Keyword scanner failed to confirm priority for: {missing_or_no_prio}"
        )


# ---------------------------------------------------------------------------
# Rule 4 — _drop_priority must be int (not a string)
# ---------------------------------------------------------------------------

class TestDropPriorityType:
    """_drop_priority values must be integer literals in source and at runtime."""

    def test_no_string_drop_priority_in_source(self):
        """Source must not assign _drop_priority to a string literal like '\"30\"'."""
        src = _get_pb_source()
        bad = re.findall(r'"_drop_priority":\s*"[^"]*"', src)
        assert not bad, (
            f"_drop_priority assigned as a string literal in prompt_builder: {bad}. "
            "Use integer literals only (e.g. `\"_drop_priority\": 30`)."
        )

    def test_all_declared_priorities_are_positive_ints(self):
        """Every _drop_priority value extracted from source is a positive int."""
        src = _get_pb_source()
        for name, prio in _extract_layers_from_source(src):
            if prio is not None:
                assert isinstance(prio, int), (
                    f"Layer {name!r}: parsed _drop_priority={prio!r} is not int"
                )
                assert prio > 0, (
                    f"Layer {name!r}: _drop_priority={prio!r} must be > 0"
                )

    def test_promptlayer_accepts_int_drop_priority(self):
        from core.prompt_layer import PromptLayer
        layer = PromptLayer(name="6c_episodic", content="x", drop_priority=70)
        assert isinstance(layer.drop_priority, int)
        assert layer.drop_priority == 70

    def test_promptlayer_accepts_none_drop_priority(self):
        from core.prompt_layer import PromptLayer
        layer = PromptLayer(name="1_system_prompt", content="x")
        assert layer.drop_priority is None

    def test_prompt_layer_to_message_embeds_int(self):
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="6b_event_search", content="x", drop_priority=30)
        msg = prompt_layer_to_message(layer)
        assert isinstance(msg["_drop_priority"], int)
        assert msg["_drop_priority"] == 30


# ---------------------------------------------------------------------------
# Rule 5 — Duplicate _drop_priority values are explicitly permitted
# ---------------------------------------------------------------------------

class TestSamePriorityBatchSemantics:
    """
    R4-B: same-priority messages are dropped as an atomic batch.
    6e_inner_diary (facts + feeling) intentionally share priority=60.
    This rule confirms the design: no uniqueness constraint on _drop_priority.
    """

    def test_6e_inner_diary_shares_priority_60(self):
        """
        Both 6e_inner_diary_facts and 6e_inner_diary_feeling emit _layer="6e_inner_diary"
        with _drop_priority=60 so they are dropped together.
        """
        src = _get_pb_source()
        # Find all occurrences of "6e_inner_diary" layer with their priorities
        all_pairs = _extract_layers_from_source(src)
        diary_entries = [(n, p) for n, p in all_pairs if n == "6e_inner_diary"]
        assert len(diary_entries) >= 2, (
            "Expected at least 2 append blocks for '6e_inner_diary' (facts + feeling); "
            f"found {len(diary_entries)}."
        )
        for name, prio in diary_entries:
            assert prio == 60, (
                f"6e_inner_diary entry has _drop_priority={prio!r}, expected 60."
            )

    def test_promptlayer_allows_shared_priority(self):
        """Two PromptLayer objects may carry the same drop_priority without error."""
        from core.prompt_layer import PromptLayer
        a = PromptLayer(name="layer_a", content="x", drop_priority=60)
        b = PromptLayer(name="layer_b", content="y", drop_priority=60)
        # No exception; shared priority is valid by design
        assert a.drop_priority == b.drop_priority == 60

    def test_priority_not_globally_unique_across_known_layers(self):
        """
        DROPPABLE_LAYER_PRIORITIES itself uses unique values (by convention),
        but the trimmer does NOT enforce uniqueness — only ordering matters.
        Confirm: no assertion error when priorities are equal in trimmer logic.
        """
        # Simulate the R4-B trimmer with two layers at the same priority
        msgs = [
            {"role": "system", "content": "A" * 16000, "_layer": "base"},
            {"role": "system", "content": "B" * 2000, "_layer": "layer_x", "_drop_priority": 55},
            {"role": "system", "content": "C" * 2000, "_layer": "layer_y", "_drop_priority": 55},
            {"role": "system", "content": "hi",        "_layer": "user"},
        ]
        import copy
        msgs = copy.deepcopy(msgs)
        token_estimate = sum(len(m["content"]) for m in msgs)  # 20002 → over limit
        assert token_estimate > 20000

        droppable = [(i, m) for i, m in enumerate(msgs) if m.get("_drop_priority") is not None]
        droppable.sort(key=lambda x: (x[1]["_drop_priority"], x[0]))
        drop_indices: set[int] = set()
        di = 0
        while di < len(droppable) and token_estimate > 18000:
            cur = droppable[di][1]["_drop_priority"]
            while di < len(droppable) and droppable[di][1]["_drop_priority"] == cur:
                idx, msg = droppable[di]
                drop_indices.add(idx)
                token_estimate -= len(msg["content"])
                di += 1
        trimmed = [m for j, m in enumerate(msgs) if j not in drop_indices]
        trimmed_names = {m["_layer"] for m in trimmed}
        assert "layer_x" not in trimmed_names
        assert "layer_y" not in trimmed_names


# ---------------------------------------------------------------------------
# Rule 6 — PromptLayer→message contract
# ---------------------------------------------------------------------------

class TestPromptLayerToMessageContract:
    """
    Verifies the stable PromptLayer→message dict conversion contract.
    This is the baseline from R4-A; R4-C confirms it has not regressed.
    """

    def test_none_drop_priority_omits_field(self):
        """drop_priority=None must NOT write _drop_priority into the message."""
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="1_system_prompt", content="x")
        msg = prompt_layer_to_message(layer)
        assert "_drop_priority" not in msg

    def test_int_drop_priority_embeds_field(self):
        """drop_priority=N must write _drop_priority=N into the message."""
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="6c_episodic", content="x", drop_priority=70)
        msg = prompt_layer_to_message(layer)
        assert "_drop_priority" in msg
        assert msg["_drop_priority"] == 70

    def test_name_written_as_layer_key(self):
        """layer.name → msg["_layer"]."""
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="mid_term", content="x")
        msg = prompt_layer_to_message(layer)
        assert msg["_layer"] == "mid_term"

    def test_role_written_correctly(self):
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="x", content="y", role="user")
        msg = prompt_layer_to_message(layer)
        assert msg["role"] == "user"

    def test_content_preserved(self):
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="x", content="hello world")
        msg = prompt_layer_to_message(layer)
        assert msg["content"] == "hello world"

    def test_sanitize_strips_drop_priority_and_layer(self):
        """sanitize_messages() must strip _drop_priority and _layer before LLM calls."""
        from core.prompt_layer import sanitize_messages
        msg = {"role": "system", "content": "x", "_layer": "6b", "_drop_priority": 30}
        result = sanitize_messages([msg])
        assert "_drop_priority" not in result[0]
        assert "_layer" not in result[0]
        assert result[0]["content"] == "x"  # content preserved

    def test_sanitize_does_not_mutate_originals(self):
        from core.prompt_layer import sanitize_messages
        original = {"role": "system", "content": "x", "_layer": "test", "_drop_priority": 5}
        sanitize_messages([original])
        assert "_layer" in original, "sanitize_messages mutated the original dict"
        assert "_drop_priority" in original

    def test_non_droppable_layer_message_has_no_priority(self):
        """A non-droppable layer's message must not carry _drop_priority."""
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="11_author_note", content="rules")  # drop_priority=None
        msg = prompt_layer_to_message(layer)
        assert "_drop_priority" not in msg
        assert msg["_layer"] == "11_author_note"

    def test_default_role_is_system(self):
        from core.prompt_layer import PromptLayer, prompt_layer_to_message
        layer = PromptLayer(name="x", content="y")
        msg = prompt_layer_to_message(layer)
        assert msg["role"] == "system"

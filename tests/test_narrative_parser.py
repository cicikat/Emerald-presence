"""
tests/test_narrative_parser.py — Phase 1 parser unit tests.

Requirement coverage (numbered per spec):
  1. 纯文本 → 一个 narration segment，content 等于原文
  2. <say>你好</say> → say segment，content 为"你好"
  3. 裸文本 + <say> 混合 → narration + say
  4. <do> / <env> / <feel> 均可识别
  5. 未知标签不丢内容
  6. 未闭合标签不抛异常
  7. 空标签不产生脏 segment
  8. 多段同类标签顺序保留
  9. 解析异常 fallback 不影响 content
"""

import pytest
from core.narrative_parser import parse_narrative_segments


# ── helpers ──────────────────────────────────────────────────────────────────

def _types(result):
    return [s["type"] for s in result["segments"]]


def _texts(result):
    return [s["text"] for s in result["segments"]]


def _all_text(result):
    return " ".join(s["text"] for s in result["segments"])


# ═══════════════════════════════════════════════════════════════════════════════
# Case 1 — 纯文本
# ═══════════════════════════════════════════════════════════════════════════════

def test_plain_text_single_narration_segment():
    r = parse_narrative_segments("hello world")
    assert _types(r) == ["narration"]
    assert r["segments"][0]["text"] == "hello world"
    assert r["content"] == "hello world"


def test_plain_text_chinese():
    r = parse_narrative_segments("她低着头，沉默了很久。")
    assert _types(r) == ["narration"]
    assert r["content"] == "她低着头，沉默了很久。"


# ═══════════════════════════════════════════════════════════════════════════════
# Case 2 — 单个 <say> 标签
# ═══════════════════════════════════════════════════════════════════════════════

def test_say_tag_segment_type_and_text():
    r = parse_narrative_segments("<say>你好</say>")
    assert _types(r) == ["say"]
    assert r["segments"][0]["text"] == "你好"


def test_say_tag_content_stripped():
    r = parse_narrative_segments("<say>你好</say>")
    assert r["content"] == "你好"
    assert "<say>" not in r["content"]
    assert "</say>" not in r["content"]


# ═══════════════════════════════════════════════════════════════════════════════
# Case 3 — 裸文本 + <say> 混合
# ═══════════════════════════════════════════════════════════════════════════════

def test_mixed_narration_and_say_order():
    r = parse_narrative_segments("她抬起头，<say>你在哪里？</say>声音很轻。")
    assert _types(r) == ["narration", "say", "narration"]


def test_mixed_say_text_content():
    r = parse_narrative_segments("她说：<say>再见</say>，然后走了。")
    say_segs = [s for s in r["segments"] if s["type"] == "say"]
    assert say_segs[0]["text"] == "再见"
    assert "<" not in r["content"]


# ═══════════════════════════════════════════════════════════════════════════════
# Case 4 — do / env / feel 均可识别
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tag", ["do", "env", "feel"])
def test_each_known_tag_recognized(tag):
    r = parse_narrative_segments(f"<{tag}>test content</{tag}>")
    assert len(r["segments"]) == 1
    assert r["segments"][0]["type"] == tag
    assert r["segments"][0]["text"] == "test content"


def test_all_four_known_tags_together():
    reply = "<say>对白</say><do>动作</do><env>环境</env><feel>感受</feel>"
    r = parse_narrative_segments(reply)
    assert _types(r) == ["say", "do", "env", "feel"]
    # content has no markup
    assert "<" not in r["content"]
    assert "对白" in r["content"]
    assert "感受" in r["content"]


# ═══════════════════════════════════════════════════════════════════════════════
# Case 5 — 未知标签不丢内容
# ═══════════════════════════════════════════════════════════════════════════════

def test_unknown_tag_content_not_lost_in_segments():
    r = parse_narrative_segments("<unknown>some text</unknown>")
    assert "some text" in _all_text(r)


def test_unknown_tag_content_not_lost_in_content():
    r = parse_narrative_segments("<mystery>hidden content</mystery>")
    assert "hidden content" in r["content"]


def test_unknown_tag_produces_no_own_type_segment():
    r = parse_narrative_segments("<xyz>stuff</xyz>")
    for seg in r["segments"]:
        assert seg["type"] != "xyz"


def test_unknown_tag_mixed_with_known():
    r = parse_narrative_segments("<say>hello</say><br/>world")
    # "hello" in say segment, "world" in narration, "<br/>" treated as unknown
    say_segs = [s for s in r["segments"] if s["type"] == "say"]
    assert say_segs[0]["text"] == "hello"
    combined = _all_text(r)
    assert "world" in combined


# ═══════════════════════════════════════════════════════════════════════════════
# Case 6 — 未闭合标签不抛异常
# ═══════════════════════════════════════════════════════════════════════════════

def test_unclosed_known_tag_no_exception():
    # Must not raise
    r = parse_narrative_segments("<say>没有闭合")
    assert isinstance(r, dict)
    assert "content" in r
    assert "segments" in r


def test_unclosed_tag_content_preserved():
    r = parse_narrative_segments("<say>对白没闭合")
    assert "对白没闭合" in _all_text(r)


def test_unclosed_tag_text_accessible():
    r = parse_narrative_segments("前缀 <feel>内心独白没闭合")
    combined = _all_text(r)
    assert "内心独白没闭合" in combined


# ═══════════════════════════════════════════════════════════════════════════════
# Case 7 — 空标签不产生脏 segment
# ═══════════════════════════════════════════════════════════════════════════════

def test_empty_known_tag_no_segment():
    r = parse_narrative_segments("<say></say>")
    say_segs = [s for s in r["segments"] if s["type"] == "say"]
    assert say_segs == []


def test_whitespace_only_tag_no_segment():
    r = parse_narrative_segments("<do>   </do>")
    do_segs = [s for s in r["segments"] if s["type"] == "do"]
    assert do_segs == []


def test_all_segments_have_nonempty_text():
    r = parse_narrative_segments("<say></say><do>  </do><env>content</env>")
    for seg in r["segments"]:
        assert seg["text"].strip() != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Case 8 — 多段同类标签顺序保留
# ═══════════════════════════════════════════════════════════════════════════════

def test_multiple_same_tag_order_preserved():
    r = parse_narrative_segments("<say>A</say><say>B</say><say>C</say>")
    say_segs = [s for s in r["segments"] if s["type"] == "say"]
    assert [s["text"] for s in say_segs] == ["A", "B", "C"]


def test_interleaved_tags_order_preserved():
    r = parse_narrative_segments("<say>说话</say><do>动作</do><say>再说</say>")
    assert _types(r) == ["say", "do", "say"]


def test_many_segments_relative_order():
    reply = "叙述1 <say>S1</say> 叙述2 <do>D1</do> 叙述3"
    r = parse_narrative_segments(reply)
    types = _types(r)
    # narration → say → narration → do → narration
    assert types.index("say") < types.index("do")


# ═══════════════════════════════════════════════════════════════════════════════
# Case 9 — 解析异常 fallback
# ═══════════════════════════════════════════════════════════════════════════════

def test_exception_fallback_content_equals_reply(monkeypatch):
    import core.narrative_parser as _mod

    def _raise(_reply):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(_mod, "_parse", _raise)

    raw = "fallback text"
    r = parse_narrative_segments(raw)
    assert r["content"] == raw


def test_exception_fallback_single_narration_segment(monkeypatch):
    import core.narrative_parser as _mod

    def _raise(_reply):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(_mod, "_parse", _raise)

    raw = "fallback text"
    r = parse_narrative_segments(raw)
    assert len(r["segments"]) == 1
    assert r["segments"][0]["type"] == "narration"
    assert r["segments"][0]["text"] == raw


# ═══════════════════════════════════════════════════════════════════════════════
# Extra edge cases
# ═══════════════════════════════════════════════════════════════════════════════

def test_empty_string_returns_no_segments():
    r = parse_narrative_segments("")
    assert r["content"] == ""
    assert r["segments"] == []


def test_original_reply_not_mutated():
    raw = "<say>不变</say>"
    parse_narrative_segments(raw)
    assert raw == "<say>不变</say>"


def test_content_has_no_angle_brackets():
    r = parse_narrative_segments("前 <say>说</say> 后 <do>做</do>")
    assert "<" not in r["content"]
    assert ">" not in r["content"]


def test_multiline_reply():
    reply = "她走进房间。\n<say>你好啊。</say>\n<feel>心里有点紧张。</feel>"
    r = parse_narrative_segments(reply)
    types = _types(r)
    assert "narration" in types
    assert "say" in types
    assert "feel" in types

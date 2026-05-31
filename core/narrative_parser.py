"""
core/narrative_parser — Emerald Narrative Message Protocol Phase 1 parser.

Parses an LLM reply into typed narrative segments without touching the
original reply string.  The raw reply is the source of truth for all
archive / history / event_log chains; segments are a read-only view.

Supported protocol tags: <say>, <do>, <env>, <feel>
Any other tag-like token is treated as literal narration text so no
content is ever lost.

Usage::

    from core.narrative_parser import parse_narrative_segments
    result = parse_narrative_segments(reply)
    # result["content"]  — tag-markup stripped plain text
    # result["segments"] — list of {"type": ..., "text": ...}

This module intentionally has zero imports from dreams/, impression_loader,
afterglow, dream_summary, DataPaths, or any reality/dream data path.
"""

import re
from typing import TypedDict

KNOWN_TAGS: frozenset[str] = frozenset({"say", "do", "env", "feel"})

# Matches any XML-like open or close token: <word> or </word>
_TAG_TOKEN_RE = re.compile(r"<(/?)([\w]+)>")
# Strips all XML-like tag markers for building the clean content string
_ALL_TAG_RE = re.compile(r"</?[a-zA-Z]\w*>")


class NarrativeSegment(TypedDict):
    type: str   # "say" | "do" | "env" | "feel" | "narration"
    text: str


class NarrativeParseResult(TypedDict):
    content: str   # tag-markup stripped plain text
    segments: list  # list[NarrativeSegment]


def parse_narrative_segments(reply: str) -> NarrativeParseResult:
    """
    Parse *reply* into narrative segments.  Never raises; any internal error
    returns a safe fallback where the full reply is a single narration segment
    and content equals the original reply.
    """
    try:
        return _parse(reply)
    except Exception:
        return {
            "content": reply,
            "segments": [{"type": "narration", "text": reply}],
        }


# ─────────────────────────────────────────────────────────────────────────────

def _parse(reply: str) -> NarrativeParseResult:
    # Phase 1: tokenise
    # Each token is ("text"|"open_known"|"close_known", value)
    # Unknown tags are kept as literal "text" tokens so content is never lost.
    tokens: list[tuple[str, str]] = []
    pos = 0
    for m in _TAG_TOKEN_RE.finditer(reply):
        start, end = m.span()
        if start > pos:
            tokens.append(("text", reply[pos:start]))
        is_close = m.group(1) == "/"
        tag = m.group(2).lower()
        if tag in KNOWN_TAGS:
            tokens.append(("close_known" if is_close else "open_known", tag))
        else:
            # Unknown tag: preserve as literal text so no content is dropped
            tokens.append(("text", m.group(0)))
        pos = end
    if pos < len(reply):
        tokens.append(("text", reply[pos:]))

    # Phase 2: build segments with a single-level tag stack
    segments: list[NarrativeSegment] = []
    current_tag: str | None = None
    buf: list[str] = []

    def _flush(seg_type: str) -> None:
        text = "".join(buf).strip()
        buf.clear()
        if text:
            segments.append({"type": seg_type, "text": text})

    for kind, value in tokens:
        if kind == "text":
            buf.append(value)
        elif kind == "open_known":
            if current_tag is None:
                _flush("narration")
                current_tag = value
            else:
                # Nested open tag inside an already-open known tag:
                # fold it in as literal text rather than trying to nest.
                buf.append(f"<{value}>")
        elif kind == "close_known":
            if current_tag == value:
                _flush(current_tag)
                current_tag = None
            else:
                # Orphaned or mismatched close tag: literal text, no content lost
                buf.append(f"</{value}>")

    # Flush remaining buffer.
    # If current_tag is set the tag was never closed; auto-close it here
    # (simpler and safer than downgrading to narration since the LLM intent
    # is clear even without the closing marker).
    _flush(current_tag if current_tag is not None else "narration")

    # Phase 3: build clean content string
    content = _ALL_TAG_RE.sub("", reply).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = re.sub(r" {2,}", " ", content)

    return {"content": content, "segments": segments}

"""Prompt-style transform hook.

Called in llm_client BEFORE sanitize_messages so that _layer metadata is
still available for XML tag generation.

Styles:
  narrative (default) — no-op, passes messages unchanged (current behaviour).
  xml — wraps each system-role message in <layer_name>…</layer_name> tags,
        using the _layer field as the tag name (sanitised to [a-zA-Z0-9_]).
        user / assistant messages are left untouched.
        Ordering, merging, and drop_priority trimming are NOT changed here.
"""
from __future__ import annotations

import re

_TAG_SAFE_RE = re.compile(r"[^a-zA-Z0-9_]")


def _safe_tag(name: str) -> str:
    safe = _TAG_SAFE_RE.sub("_", name)
    return safe or "context"


def _to_xml(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.get("role") != "system":
            out.append(m)
            continue
        layer = m.get("_layer") or "context"
        tag = _safe_tag(layer)
        new_m = dict(m)
        new_m["content"] = f"<{tag}>{m['content']}</{tag}>"
        out.append(new_m)
    return out


def apply_prompt_style(messages: list[dict], style: str) -> list[dict]:
    """Transform messages for the target prompt style.

    Must be called BEFORE sanitize_messages — the _layer field is consumed
    here and then stripped by sanitize.
    """
    if style == "xml":
        return _to_xml(messages)
    return messages  # "narrative" and any unknown style: pass through

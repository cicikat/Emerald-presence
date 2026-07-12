"""Markdown-level technique notes (Brief 60)."""
from __future__ import annotations
import re
import time

from core.data_paths import DEFAULT_CHAR_ID

MAX_NOTES = 20
MAX_NOTE_CHARS = 40
MAX_PROMPT_CHARS = 800
STALE_ZERO_HIT_DAYS = 60
_LINE_RE = re.compile(r"^- (.*?)\s*<!-- ts:([0-9.]+) src:([^ ]+) hits:(\d+) -->$")

def _path(interest_id: str, char_id: str):
    from core.sandbox import get_paths
    return get_paths().growth_note(interest_id, char_id=char_id)

def load(interest_id: str, *, char_id: str = DEFAULT_CHAR_ID) -> list[dict]:
    path = _path(interest_id, char_id)
    if not path.exists(): return []
    result=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        m=_LINE_RE.match(line.strip())
        if m: result.append({"text":m.group(1),"ts":float(m.group(2)),"src":m.group(3),"hits":int(m.group(4))})
    return result

def _save(interest_id: str, entries: list[dict], char_id: str) -> None:
    from core.safe_write import safe_write_text
    path=_path(interest_id,char_id); path.parent.mkdir(parents=True,exist_ok=True)
    text="\n".join(f"- {e['text']} <!-- ts:{e['ts']} src:{e['src']} hits:{e['hits']} -->" for e in entries)
    safe_write_text(path, text + ("\n" if text else ""))

def prompt_text(interest_id: str, *, char_id: str = DEFAULT_CHAR_ID) -> str:
    return "\n".join(f"- {e['text']}" for e in load(interest_id,char_id=char_id))[:MAX_PROMPT_CHARS]

def _similar(a: str, b: str) -> bool:
    def grams(s): s=re.sub(r"\s+","",s); return {s[i:i+2] for i in range(max(1,len(s)-1))}
    ga,gb=grams(a),grams(b); return bool(ga and gb and len(ga&gb)/max(1,min(len(ga),len(gb)))>=0.7)

def apply_note(interest_id: str, note: str | None, *, source: str, replaces: int | None = None, char_id: str = DEFAULT_CHAR_ID, uid: str = "") -> bool:
    if not note: return False
    note=str(note).strip()[:MAX_NOTE_CHARS]
    entries=load(interest_id,char_id=char_id)
    new={"text":note,"ts":time.time(),"src":source,"hits":0}
    replace_index=replaces-1 if isinstance(replaces,int) and 1 <= replaces <= len(entries) else None
    if any(_similar(note,e["text"]) for index,e in enumerate(entries) if index != replace_index): return False
    if replace_index is not None: entries[replace_index]=new
    elif len(entries)<MAX_NOTES: entries.append(new)
    else:
        idx=min(range(len(entries)),key=lambda i:(entries[i]["hits"],entries[i]["ts"])); entries[idx]=new
    _save(interest_id,entries,char_id)
    try:
        from core.memory import provenance_log
        provenance_log.append(uid or "system",char_id,artifact="growth_notes",field=interest_id,after_gist=note,trigger_signal="note_learned",origin={"source":"practice"})
    except Exception: pass
    return True

def increment_hits(interest_id: str, *, char_id: str = DEFAULT_CHAR_ID) -> None:
    entries=load(interest_id,char_id=char_id)
    if not entries: return
    for e in entries: e["hits"] += 1
    _save(interest_id,entries,char_id)

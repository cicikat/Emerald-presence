"""Capability-based MCP exposure policy (Brief 61)."""
from __future__ import annotations

from core.data_paths import DEFAULT_CHAR_ID

NEUTRAL_REFUSAL = "这项操作现在还做不了。"

def _config() -> dict:
    from core.config_loader import get_config
    value=get_config().get("mcp_proficiency",{}) or {}
    return value if isinstance(value,dict) else {}

def split_name(reg_name: str) -> tuple[str,str] | None:
    if not reg_name.startswith("mcp__"): return None
    parts=reg_name.split("__",2)
    return (parts[1],parts[2]) if len(parts)==3 else None

def _tier_entries(server_cfg: dict, level: int) -> tuple[set[str],bool,dict[str,str]]:
    tiers=server_cfg.get("tiers",{}) or {}; selected=None
    for raw_key,value in tiers.items():
        try: key=int(raw_key)
        except Exception: continue
        if key<=level and (selected is None or key>selected[0]): selected=(key,value)
    if selected is None:return set(),False,{}
    value=selected[1]; notes={}
    if isinstance(value,dict):
        tools=value.get("tools",[]); note=value.get("unlock_note")
        if isinstance(note,dict): notes={str(k):str(v) for k,v in note.items()}
        elif isinstance(note,str): notes={str(t):note for t in tools if t!="*"}
    else: tools=value
    if tools=="*": return set(),True,notes
    tools=list(tools or [])
    return {str(x) for x in tools if x!="*"}, "*" in tools, notes

def is_tool_allowed(reg_name: str, *, char_id: str = DEFAULT_CHAR_ID) -> bool:
    parsed=split_name(reg_name)
    if parsed is None:return True
    server,tool=parsed; server_cfg=_config().get(server)
    if not isinstance(server_cfg,dict): return True
    tiers=server_cfg.get("tiers",{}) or {}
    governed=set()
    for value in tiers.values():
        vals=value.get("tools",[]) if isinstance(value,dict) else value
        if vals=="*": continue
        governed.update(str(x) for x in (vals or []) if x!="*")
    # Tools never mentioned in a tier remain organ-like and always exposed.
    if tool not in governed and not any((v=="*" or (isinstance(v,list) and "*" in v) or (isinstance(v,dict) and "*" in (v.get("tools") or []))) for v in tiers.values()): return True
    from core.growth.interest_state import highest_level_for_domain
    level=highest_level_for_domain(char_id,str(server_cfg.get("domain") or ""))
    if level is None:return False
    allowed,all_tools,_=_tier_entries(server_cfg,level)
    return all_tools or tool in allowed

def filter_schemas(schemas: list[dict], *, char_id: str = DEFAULT_CHAR_ID) -> list[dict]:
    return [s for s in schemas if is_tool_allowed((s.get("function") or s).get("name",""),char_id=char_id)]

def newly_unlocked(domain: str, old_level: int, new_level: int) -> list[dict]:
    result=[]
    for server,cfg in _config().items():
        if not isinstance(cfg,dict) or cfg.get("domain")!=domain: continue
        old,old_all,_=_tier_entries(cfg,old_level); new,new_all,notes=_tier_entries(cfg,new_level)
        if new_all and not old_all:
            result.append({"server":server,"tool":"*","unlock_note":cfg.get("unlock_note") or "更多媒介方法"})
        else:
            for tool in sorted(new-old): result.append({"server":server,"tool":tool,"unlock_note":notes.get(tool) or cfg.get("unlock_note") or tool})
    return result

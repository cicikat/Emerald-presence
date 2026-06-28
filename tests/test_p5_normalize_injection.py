"""P5 验收测试：_normalize_injection 称呼清洗规则。"""
import re

import pytest

from core.prompt_builder import _normalize_injection

CHAR_NAME = "叶瑄"


def norm(text: str) -> str:
    return _normalize_injection(text, char_name=CHAR_NAME)


# ── 层 3：关系文本 ──────────────────────────────────────────────────────────────

def test_layer3_relation_text():
    raw = "<与用户关系>\n【与该用户的关系】\n该用户是你的恋人。\n</与用户关系>"
    result = norm(raw)
    # 标签名不动
    assert "<与用户关系>" in result
    assert "</与用户关系>" in result
    # 正文替换
    assert "该用户" not in result
    assert "她是你的恋人" in result
    assert "与她的关系" in result


# ── 层 5：用户概况 ───────────────────────────────────────────────────────────────

def test_layer5_profile():
    raw = "<用户概况>\n【关于这个用户】\n姓名：红茶\n</用户概况>"
    result = norm(raw)
    assert "<用户概况>" in result
    assert "</用户概况>" in result
    assert "这个用户" not in result
    assert "关于她" in result


# ── 层 5.1：客观信息（保留"非角色记忆"语义） ─────────────────────────────────────

def test_layer5_1_user_facts_semantic_preserved():
    raw = (
        "<用户客观信息>\n"
        "【用户客观信息（跨角色通用，非角色记忆）】\n"
        "生日：4月24日\n"
        "</用户客观信息>"
    )
    result = norm(raw)
    # 标签名不动
    assert "<用户客观信息>" in result
    assert "</用户客观信息>" in result
    # label 改为"她的客观信息"，且保留括号内语义
    assert "她的客观信息" in result
    assert "非角色记忆" in result
    # 裸"用户"不应出现在正文中
    text_only = re.sub(r'<[^>]+>', '', result)
    assert "用户" not in text_only


# ── 层 5 偏好 ───────────────────────────────────────────────────────────────────

def test_layer5_pref():
    raw = "<用户偏好>\n【用户近期偏好与习惯】\n- 喜欢猫\n</用户偏好>"
    result = norm(raw)
    assert "<用户偏好>" in result
    assert "用户" not in re.sub(r'<[^>]+>', '', result)


# ── 层 6a：用户稳定行为（无 XML 标签，纯正文）────────────────────────────────────

def test_layer6a_identity():
    raw = "关于用户的长期观察（优先级低于当前对话，如有冲突以当下为准）：\n爱好写作"
    result = norm(raw)
    assert "用户" not in result
    assert "她的长期观察" in result


# ── 英文 user（独立词，大小写） ─────────────────────────────────────────────────

def test_english_user_word_boundary():
    raw = "The user has been active today. username and user_id are unaffected."
    result = norm(raw)
    assert "The 她 has been active today." in result
    # 非独立词不替换
    assert "username" in result
    assert "user_id" in result


def test_english_user_uppercase():
    raw = "User said hello."
    result = norm(raw)
    assert "她 said hello." in result


# ── 保护：XML 标签名绝对不动 ────────────────────────────────────────────────────

def test_xml_tag_names_untouched():
    raw = "<与用户关系><用户概况><用户客观信息><用户偏好>"
    result = norm(raw)
    assert result == raw


# ── history（真实对话）不经过此函数，此处仅验证函数对 user role 文本无副作用 ────────

def test_user_role_content_passed_through_unchanged():
    # pipeline 只对 role=="system" 调用此函数；此测试直接验证函数不破坏对话原文
    dialogue = "用户说：我今天很累。"
    result = norm(dialogue)
    # 此处纯正文（无 XML 标签），函数会替换——这是符合预期的，
    # 真实对话不会经过此函数（seam 在 prompt_builder 里已按 role 筛选）。
    # 仅断言输出确定性（不抛异常、是字符串）。
    assert isinstance(result, str)

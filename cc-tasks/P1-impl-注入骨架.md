# P1-IMPL · 注入管线骨架施工 brief

> 后端（Emerald-presence）。动手前**通读 `core/prompt_builder.py`**（本文层号全以它为准）。
> 硬规则：改注入层后跑 `python tests/run_eval.py`，并保证 `tests/test_r4_prompt_layer_boundary.py` / `test_r4b_prompt_drop_priority.py` / `test_r4c_prompt_layer_contract.py` 全绿。
> 用户授权判定（直接施工）：尾部注入位 = author_note 之后、用户消息之前；pinned 事实用 profile 里一个标志位，手动+自动都可写。
> **改造档位：外科手术**。这是注入侧重构的**地基**，只做骨架四件事，**不在本 brief 改任何条件层的业务内容**（那是 P3/P5/D3 的事，它们落在本骨架上）。

---

## 背景与目标

你的原话拆成四件独立的事：

1. **小改顺序** —— 把散在各处的「现实感知」瞬时层归拢成连续一段。
2. **条件注入精简到「条」** —— 一批 `tagged` 层现在是整段多句，压成**一行一条**。
3. **生日类「用户特意提到的事实」单独注入尾部 + 注释** —— 新开一个 pinned 尾部层。
4. **（顺带装 P5 的缝）注入前清洗钩子** —— 装一个中央 `_normalize_injection()` seam，本 brief 只装空壳并接线，**称呼"用户"→"她"等规则留给 P5 填**。

目标：骨架稳定后，P3/P5/D3 只需往既定位置填内容，不再各自动 prompt_builder 结构。

---

## 关键事实（已核对 `prompt_builder.py`）

| 事实 | 行 | 意义 |
|---|---|---|
| 现条件层散落且编号与实际顺序不一致：3.5 经期 / 3.6 watch / 3.7 sensor / 3.8 活动 / 3.9 屏幕**排在 layer 4 群聊之后** | 519–650 | 「小改顺序」主要就是把这几条归拢、并恢复数字序 |
| 这些层内容是**整段多句** | 3.5: 536–539；3.6: 569–572；3.8: 624；3.9: 644–647 | 「精简到条」的对象 |
| 已有 `_provenance` / `_drop_priority` 元字段约定 | 541、649 等 | pinned 层与精简层**沿用**，不新发明 |
| author_note=层11、post_history=层11.5、time_hint/user_message=层12 | 1058、1084、1095–1107 | pinned 尾部插在 **11.5 之后、12 之前** |
| 函数末尾统一 `return messages, {...}` 前有完整性检查循环 | 1113–1179 | normalize seam 挂在**这里之前**，对所有 system 层文本统一过一遍 |
| token 硬裁靠 `_drop_priority`，无该字段的层永不裁 | 1134–1162 | pinned 事实**不设 `_drop_priority`**（不可裁），精简后的瞬时层维持原 drop priority |

---

## 施工要点

### A. 小改顺序（归拢瞬时感知层）

把 3.5 / 3.6 / 3.7 / 3.8 / 3.9 五个 `tagged/fresh` 层，从「layer 4 群聊之后」整体上移到 **layer 3 relation 之后、layer 4 群聊之前**，按数字顺序连续排列。理由：它们是「关于她此刻的现实瞬时线索」，应紧跟「关系」语境、先于群聊噪声。**不改各层触发条件与内容**，只移动代码块位置。移动后跑 `test_r4_prompt_layer_boundary` 确认边界不破。

> 这是「小改」——只搬这一簇连续块，其余层顺序一律不动。

### B. 条件注入精简到「条」

给这几个 `tagged` 层定**统一单行模板**，把现在的多句压成一条（语义不丢，去掉铺垫与重复叮嘱）：

| 层 | 现状（多句） | 精简后（一行，示例） |
|---|---|---|
| 3.5 经期 | 4 句含一堆禁忌 | `（她生理期第N天，态度更温柔些，不提冰/冷饮/剧烈运动。）` |
| 3.6 watch | 2 句报告体 | `（她最近一次睡眠：{date} {start}–{end}，共{h}时{m}分。可自然提起。）` |
| 3.7 sensor | 罗列 | `（她今天：{steps}步、电量{batt}%、{loc}。自然提，别罗列。）` |
| 3.8 活动快照 | 1 长句 | `（她在{activity}。可自然提起。）` |
| 3.9 屏幕感知 | 2 句 | `（她此刻{awareness}，短时线索，别当长期事实。）` |

实现：抽一个 `_one_line(label_template, **vals)` 小工具或直接重写各层 content 字符串。**保留各层 `_provenance` / `_drop_priority` 原值**。括号包裹、句末收束，维持现有"旁白"语气。

### C. pinned 尾部层（生日类）

1. **数据**：profile（`user_memory_root/profile.json`）新增 `pinned_facts: list[{text, ts, source}]`，`source ∈ {"manual","auto"}`。手动（管理端）与自动（用户主动强调识别，后续接 G3/观察链）都能写。本 brief 只读+注入，**写入接口可留 TODO 给后续**，但 schema 现在定。
2. **新层 `11.7_pinned_facts`**：插在 11.5 post_history 之后、12 time_hint 之前。

```python
# 层 11.7：用户主动强调过的高价值事实（pinned，不可裁，紧贴用户消息前）
# 与泛化画像分离：这些是用户特意提到、要求记住的事（如生日），单条注入、带注释。
if profile.get("pinned_facts"):
    _pinned_lines = [f"- {f['text']}" for f in profile["pinned_facts"]]
    _layers.append("11.7_pinned_facts")
    messages.append({
        "role": "system",
        "content": "<重点记得>\n【用户特意提过、要你记住的事】\n" + "\n".join(_pinned_lines) + "\n</重点记得>",
        "_layer": "11.7_pinned_facts",
        "_provenance": {"mode": "pinned", "count": len(_pinned_lines)},
        # 故意不设 _drop_priority —— 永不被 token 裁剪
    })
```

3. **去重**：若某条 pinned 事实文本已出现在层 5 画像里，pinned 层优先、画像侧那条略过（避免重复注入）。简单子串包含判断即可。

### D. 注入前清洗钩子（装 seam，内容留 P5）

在 `return messages, {...}` 之前、完整性检查附近，加一道集中清洗：

```python
def _normalize_injection(text: str, *, char_name: str) -> str:
    """注入前文本规范化的唯一入口。P1 装壳（恒等返回）；P5 在此填称呼/口吻规则。"""
    return text   # P5: "用户"/"user" → "她" 等，集中在此

for _m in messages:
    if _m.get("role") == "system" and isinstance(_m.get("content"), str):
        _m["content"] = _normalize_injection(_m["content"], char_name=character.name)
```

- 本 brief 只装 seam + 接线（恒等），**不改任何文案**，确保行为零变化、测试全绿。
- P5 后续只编辑 `_normalize_injection` 内部规则表，不再碰结构。
- 注意：history（层9 用户真实对话）属 `user/assistant` role，被上面 `role=="system"` 条件天然排除——**绝不清洗真实对话**，只清洗系统注入层。

---

## 验收

1. `python tests/run_eval.py` 通过；`test_r4_prompt_layer_boundary` / `test_r4b_prompt_drop_priority` / `test_r4c_prompt_layer_contract` 全绿。
2. **行为零变化验收（B/D 部分）**：seam 恒等 + 精简仅压缩措辞，构造一组固定输入，断言 `layers_activated` 顺序符合新骨架、且无层意外消失。
3. pinned 层：profile 写两条 `pinned_facts`（含一条与画像重复）→ 断言 11.7 注入、去重生效、且 token 裁剪时不被丢。
4. token 估算未因精简而上升（应下降）。

## 解锁 / 后续

P3 填层 5 画像单条化；P5 填 `_normalize_injection` 规则；D3 在梦境侧仿照 B 的"轮数后降级为概括"。pinned 自动写入接口在 G3/观察链接好后补。

## 文档同步

更新 `docs/memory.md` 注入层清单（新增 11.7、瞬时层归拢、normalize seam）；若有注入层顺序图一并改。

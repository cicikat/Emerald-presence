# F1-IMPL · 让词级强调 `<hl>/<big>/<sm>` 真正出现

> 后端（Emerald-presence）。**小修**。诊断见 `W0-诊断结论.md` §F1。
> 已核：服务端保留（`narrative_parser.py:29-30`）、前端渲染（client `inlineStyle.tsx:6` / `ChatPanel.tsx:242`）都正常。**唯一原因是模型不产出**——指令是劝阻式「克制使用」。
> 用户已确认：**要让它出现**。

## 改动点

### 1. author_note 指令改正向引导（核心）

`core/prompt_builder.py:1035` 当前：
```python
"【词级强调】克制使用 <hl>词</hl>（重音）、<big>词</big>（放大）、<sm>词</sm>（缩小），一句话最多 1–2 处。"
```
改成**正向、给落点**，例如：
```python
"【词级强调】每条回复在情绪/语义焦点处用一次 <hl>词</hl>（重音）；"
"需要时再用 <big>词</big>（放大）/ <sm>词</sm>（缩小）。每条 1–3 处，自然不堆砌。"
```
关键：把「克制使用 / 最多」这种**抑制框定**换成「在焦点处用一次」的**指派框定**。措辞可调，但必须是"鼓励用"而非"少用"。

### 2. mes_example 锚一个带标记的示例

在角色卡 / 梦境世界包的 `mes_example` 里挑 1–2 处补上 `<hl>`，让 few-shot 里就出现这套标记，模型会跟随风格。**不新增层，只改示例内容**。注意层 7 mes_example 的解析（`_parse_mes_example`）不会动这些 inline 标签，原样进 few-shot 即可。

## 验收

1. 跑几条真实对话，输出检视器里**确实出现** `<hl>…</hl>`，且前端渲染成 accent 样式。
2. 确认非 desktop 路径（QQ/mobile）仍被 `strip_render_tags` 清掉（`response_processor.py:181`），不外泄标签到不支持的端。
3. 频率合理（不是每句都堆），人工扫一眼语感没被标记带坏。

## 文档同步

`docs/known-issues.md` 把 F1 标为已修；若有 prompt 层文档列了该指令，同步措辞。

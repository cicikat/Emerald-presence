# Brief 106 · private_exchange 身份注入与语域修复

> 背景：真机观察到角色私下往来中互相错认成恋人、上文不接下语。
> 根因已定位（下述 file:line 均已核实），按序修，§1 是主修。

## 1. 🔴 render_private_presence 丢失双方身份（主因）

`core/stage/context.py:104`：`render_private_presence(_viewer_id, _other_id)`
两参数收而不用，产出只有语域两句，角色不知道自己是谁、对面是谁。
角色卡唯一亲密关系模板是对用户的 → 模型把"私下+亲昵语域"错套成恋人关系。

修法：保留现有两句（决策 9.5 反漂移锚，勿删），前面补身份段：
- `你是{viewer_name}，现在深夜和{other_name}单独说上了话。`
- 注入双方既有印象（复用 `char_relations.viewer_summary(viewer, other)`，
  有才注，无则略）——群聊版 render_presence:24-44 已有同款模式可参照。

## 2. 🟡 私聊 transcript 层头误标"群聊"

`core/prompt_builder.py:849`：4.2 层固定拼"【当前群聊共享对话】"。私聊复用
此槽位时被标成群聊。修法：加参数或按内容区分，私聊场景改为
"【你们俩的私下对话（{user}不在场）】"。层名 `_layer` 保持不变。

## 3. 🟡 指令以 user 角色注入，易被读成"有人在场发话"

`core/stage/views.py:178-185`：instruction（"接着刚才的话往下聊…"）经
build_prompt 走 user 槽位。评估改为 system 尾注或在文本前加"（旁白指引，
不是任何人的发言）"前缀；两案选实测连贯性更好的（用 §5 检视器对比）。

## 4. 🟡 群聊 Stage：1:1 history 与群 transcript 混注（需先核实）

用户触发回合走全量 fetch_context（views.py:82-91），角色与用户的 1:1
history 以裸 user/assistant 消息注入，与 4.2 群 transcript 并存，疑致
"把别人的话认成自己的"。先在 stage channel 下抓一份实际 prompt 确认，
若属实：给 history 层加显式标头"以下是你和{user}的私聊历史，不是群聊内容"，
或 stage channel 下降级/截短该层。不要凭想象改，先取证。

## 5. 🟢 检视器接线

埋点已存在：`views.py:191` `set_capture_origin({"origin": "private_exchange"})`。
查 `core/observe/prompt_capture` 落盘位置，把 private_exchange 的最近捕获
接进管理面板既有群聊观测页（参照 test_admin_group_observability_ui.py 的
现有形态），只读即可。§3/§4 的验证都依赖这个，建议先做本节。

## 验收

- 触发一次私下往来（可临时调宽深夜窗口/预算），检视器可见完整 prompt：
  含双方姓名身份段、私聊层头、指令不再像在场发言。
- 对话双方不再错认关系；transcript 前后句可衔接。
- `pytest -n auto` 通过；改动涉及 prompt 层的跑 `python tests/run_eval.py`。
- docs/stage.md 私下往来一节同步。

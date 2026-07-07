# Brief 28 · tool loop 多步工具执行器(native function calling)

> 配对文档:`Emerald-client/cc-tasks/16-tool-loop设置开关.md`(前端设置页,依赖本 brief 的 §3.7 接口)。
> 依赖:Brief 27(action_trace,loop 的跨轮记忆)已合并。
>
> 目标:让 chat preset 为 Claude/GPT/DeepSeek 这类支持 function calling 的模型时,
> 主生成可以**多步调用工具再回答**(连查多个网页→总结、自主决定查什么),而不是现在的
> "探针单发拍板、主模型不知情"。小模型(xml_fallback / probe)路径完全不动。
> 全功能挂总开关,默认关,崩坏一键回退。

---

## 1. 范围

- **只作用于 owner 真实对话轮**:QQ 私聊(main.py)与 `/desktop/chat`。群聊、scheduler 主动消息、梦境 pipeline、Stage 一律不进 loop(维持原 `run_llm`)。
- **只在 chat preset 的 `tool_call_mode == "function_calling"` 且 `tool_loop.enabled` 时激活**。xml_fallback / 探针路径零改动——小模型没有自主多步能力,这是设计边界不是遗漏。
- 不含 fs 浏览工具(后续 brief)、不含思考链、不含 MCP。

## 2. 现状盘点(已确认)

| 事实 | 位置 |
|---|---|
| `llm_client.chat(tools=)` 已支持单发 FC,模型调工具时返回 `"__TOOL_CALL__:" + json` 哨兵串,**丢弃了 tool_call id**,无法按 OpenAI 协议回填 `role="tool"` 消息 → 现有 API 撑不起多轮 loop | `core/llm_client.py:96-172` |
| 主生成调用点:`run_llm(messages)`(无 ctx,拿不到 uid/char_id/session_state,而 `execute()` 全都要)| main.py:539/624/701、admin/routers/chat.py:134(stream)/148/386/691 |
| 流式:`run_llm_stream` → `llm_client.chat_stream`(注释明确"仅用于无工具的主生成")| core/pipeline.py:659 |
| 反坍缩重试 `_anti_collapse_prefix_retry` 挂在 `run_llm` 出口 | core/pipeline.py:613 |
| `execute()` origin 白名单 `_EXECUTE_ALLOWED_ORIGINS = {user_live, assistant_intent}`,fail-closed;action_trace 已在收口埋点(Brief 27,tool_dispatcher.py:1008)| core/tool_dispatcher.py:963-1016 |
| `sanitize_messages` 只剥 `_` 前缀与 speaker_id/timestamp,`tool_calls`/`tool_call_id` 字段可存活 | core/prompt_layer.py:52 |
| **待验证**:`apply_prompt_style`(narrative/xml 转换)对 `role="tool"` 消息和带 `tool_calls` 的 assistant 消息的行为,cc 执行时必须先读 `core/prompt_style.py` 确认不被转换器吞掉/改写;若会,给这两类消息加直通豁免 | core/llm_client.py:139 |

## 3. 方案

### 3.1 `llm_client.chat_turn()`(新 API,旧 `chat()` 一字不动)

```python
@dataclass
class ChatTurn:
    content: str                      # 文本回复("" 表示纯工具轮)
    tool_calls: list[dict]            # [{id, name, arguments}],空表示终止
    assistant_message: dict           # 原样 API assistant 消息,供回填 messages

async def chat_turn(messages, tools, *, call_category="chat",
                    max_tokens_override=None) -> ChatTurn
```

- 仅支持 function_calling 模式;preset 不是该模式时抛 `ValueError`(调用方保证不会发生)。
- 复用 `chat()` 的路由/参数合并/超时/prompt_style/sanitize 全套前处理(抽公共函数,勿复制粘贴)。
- 保留 `tc.id`,assistant_message 直接存 `response.choices[0].message` 的 dict 化结果。
- 探针等既有 `chat(tools=)` 调用方继续用哨兵串,不迁移。

### 3.2 `Pipeline.run_agentic_loop()`(核心)

```python
async def run_agentic_loop(self, messages, *, uid, char_id, session_state,
                           is_group=False, stream=False)
    # 返回 str;stream=True 时返回 async generator(仅最终答案流式)
```

算法:

```
tools = get_tools_schema(categories=cfg.tool_loop.categories) 减去 cfg.tool_loop.exclude_tools
loop_msgs = list(messages)
for step in range(cfg.tool_loop.max_steps):
    turn = await chat_turn(loop_msgs, tools)
    if not turn.tool_calls:
        return turn.content                          # 自然终止
    loop_msgs.append(turn.assistant_message)
    for tc in turn.tool_calls:
        result, ask_confirm = await execute(tc.name, tc.arguments, uid, uid,
                                            is_group, session_state,
                                            origin="assistant_loop", char_id=char_id)
        loop_msgs.append({"role": "tool", "tool_call_id": tc.id,
                          "content": ask_confirm or result or "（工具无结果或执行失败）"})
# 步数耗尽 → 强制收尾:
loop_msgs.append({"role": "system", "content": _voice_reanchor(char_id)})
return await run_llm(loop_msgs 去掉 tools)            # 复用反坍缩重试出口
```

要点:

- **自然终止走 `_anti_collapse_prefix_retry`**:step≥1 后自然终止的 content 也要过一遍反坍缩检查(把终止那次调用改为经 `run_llm` 出口,或把 retry 逻辑抽成可复用函数——cc 选实现代价小的)。
- **收尾锚定 `_voice_reanchor(char_id)`**:静态模板,一句话:"工具用完了。接下来只以{char_name}的声音回复,把查到的东西揉进你自己的话里,不要报告腔、不要罗列。" char_name 经 `get_char_name()`(硬性规则8,禁字面角色名)。**只要本轮执行过 ≥1 个工具,最终生成前都注入这条**(不只是步数耗尽时)——助手腔漂移主要发生在工具轮之后。
- **单步工具异常**:execute 抛错/返回 None → 以失败文案回填 role=tool,loop 继续,让模型自己决定重试还是放弃。不因单工具失败中断整轮。
- **ask_confirm(高危工具待确认)**:把询问文字回填后**直接强制收尾**(下一步必须是问用户,不能自把自为继续)。
- **全局预算**:整个 loop 墙钟超时 `cfg.tool_loop.total_timeout_s`(默认 90s),超时按步数耗尽处理。
- **stream=True**:工具步全部非流式;终止条件达成后,最终收尾调用改走 `chat_stream`(此时已无 tools 参数,符合 chat_stream 的既有约束)逐 token yield;任何一步失败降级为非流式,语义照抄 `run_llm_stream` 的降级注释。

### 3.3 origin 与工具暴露面

- `_EXECUTE_ALLOWED_ORIGINS` 增加 `"assistant_loop"`。
- execute() 内已有的 per-origin 附加门控逐条过一遍:toy_* 的"仅 owner 真实私聊"约束对 assistant_loop 维持成立与否不重要——**默认直接排除**(见下),不给硬件工具任何自主多步入口。
- 默认暴露面(config 可调):

```yaml
tool_loop:
  enabled: false            # 总开关,默认关
  max_steps: 5
  total_timeout_s: 90
  categories: ["info", "desktop", "memory"]
  exclude_tools: ["toy_vibrate", "toy_stop", "toy_pattern", "write_toy_file"]
```

- `memory` 类进默认名单是本 brief 的顺手收益:`read_diary/search_diary/get_episodic` 等已注册未接入(docs/tools.md 明说主 LLM 无 tools schema),loop 模式下它们第一次真正可用。`get_profile/get_episodic` 与 fetch_context 自动注入重复的问题接受现状(模型多半不会重复调,调了也无害)。
- 硬件写类(`toy_*`、`write_toy_file`)默认排除:自主 loop + 执行器是危险组合,要用户在设置里显式移出 exclude 才开放。

### 3.4 与探针/路径B 的互斥

loop 激活的轮次(owner 私聊 + 开关开 + preset 是 FC 模式):

- **跳过 pre-pipeline LLM 探针**(main.py:441-451、chat.py:263-302 两处入口加同一判断,抽 `tool_loop_active(uid)` helper 到 tool_dispatcher 或 config_loader):工具决策权整体移交主模型,省一次探针调用,也消灭探针误判源。**QQ 关键词快速路径保留**(零成本,先于一切)。快速路径命中并执行后,结果照旧走 `tool_result` 注入,loop 里模型看得见(层10),不会重复执行——有 action_trace 当轮痕迹兜底。
- **跳过路径B** `_parse_and_execute_intent`(core/pipeline.py):模型在 loop 里已有完整行动机会,回复文本里的"我去帮你打开"不再触发第二次解析执行。实现:pipeline 上下文带 `loop_executed: bool`,为真则路径B直接 return。loop 未激活的轮(开关关/小模型)路径B照旧。
- 探针的 probe grounding、trusted_user_text 机制不动——loop 关掉时一切如旧。

### 3.5 loop 中间态的持久化边界

- **loop_msgs 是一次性的**:assistant tool_calls 消息、role=tool 消息不进 short_term history、不进 event_log(短期历史仍然只存 user 文本 + 最终回复,`_sanitize_assistant_message` 路径零接触)。
- 跨轮记忆全权交给 Brief 27:execute() 收口自动落 action_trace(origin=assistant_loop 一样记),下一轮层 10.5 可见、event_log_echo 可固化。**本 brief 不新增任何记忆写入点。**

### 3.6 主调用点接线

main.py 三处与 chat.py 相关处,原地分支:

```python
if tool_loop_active(uid):   # 开关 + preset FC 模式 + owner 私聊 + 非 trigger 轮
    raw_reply = await _pipeline.run_agentic_loop(messages, uid=uid, char_id=..., session_state=...)
else:
    raw_reply = await _pipeline.run_llm(messages)
```

chat.py:134 流式分支同理换 `run_agentic_loop(..., stream=True)`。
scheduler(`execution.py` 的 `_pipeline_send` 链)、群聊、stage 的调用点**不改**。

### 3.7 设置接口(前端依赖)

照 `admin/routers/settings_screen_peek.py` 的模式新增 `settings_tool_loop.py`:

- `GET /settings/tool-loop` → 当前 `tool_loop` 块 + 一个只读字段 `chat_preset_supports_fc`(当前 chat preset 是否 function_calling 模式,前端用来置灰开关并提示"当前模型不支持")。
- `POST /settings/tool-loop` → 接受 `enabled` / `max_steps`(1-8 夹取)/ `categories` / `exclude_tools`,写回 config,即时生效免重启。
- scope 沿用其他 settings 路由的既有 profile(cc 对照 `admin/scopes.py` 现表,不新开 scope)。

### 3.8 文档同步

- `docs/tools.md`:新增"路径C:tool loop"一节(激活条件、与路径A/B互斥表、暴露面与 exclude 语义)。
- `docs/model-presets.md`:`tool_call_mode` 表补一行说明 function_calling + tool_loop.enabled 的组合行为。
- `AGENTS.md` 速查表更新 `core/pipeline.py` 行描述。
- `docs/known-issues.md`:登记"loop 与 QQ 关键词快速路径可能对同一意图各执行一次(有 c2 类幂等兜底缺失)"为已知边角,列观察项。

## 4. 测试

`tests/test_tool_loop.py`,LLM 全 mock(chat_turn 按脚本吐 tool_calls 序列):

1. 自然终止:第1步无 tool_calls → 直接返回,execute 未被调用,messages 未污染。
2. 两步循环:step1 调 web_search、step2 无调用 → execute 恰好1次,role=tool 回填带正确 tool_call_id,最终 content 返回。
3. 步数耗尽:max_steps=2、脚本永远吐 tool_calls → 强制收尾调用不带 tools,且收尾 messages 含 voice_reanchor system 条目。
4. 用过工具的自然终止同样含 voice_reanchor。
5. exclude_tools:模型调 toy_vibrate → execute 层拒绝(不在 schema 里模型本调不到,双保险:schema 断言不含 excluded 项)。
6. 单步工具抛错 → loop 不中断,失败文案回填。
7. ask_confirm 非空 → 立即强制收尾,询问文字在回填里。
8. 开关关闭 / preset 非 FC / trigger 轮 → `tool_loop_active` 为假,走原 run_llm(行为零变化回归)。
9. 路径B跳过:loop_executed=True 时 `_parse_and_execute_intent` 不执行。
10. stream:脚本1步工具+终止,断言工具步非流式、最终答案经 stream 出口 yield。
11. action_trace:loop 每步 execute 落痕(origin=assistant_loop)。
12. prompt_style 直通:narrative/xml 两种 style 下 role=tool 消息内容不被改写(对应 §2 待验证项,验证结果决定是否需要豁免代码)。

## 5. 风险与回滚

- **成本/延迟**:每轮最多 1+max_steps 次主模型调用。总开关默认关;`total_timeout_s` 硬顶;前端开关(配对 brief)让用户随手关。
- **助手腔漂移**:voice_reanchor 是软手段,若不够,后续在收尾复用日记 voice anchor(`_collect_diary_voice`)加浓——本 brief 先上便宜版,观察。
- **provider 方言**:anthropic_compat 经 oneapi 网关转 OpenAI 格式,tools 协议由网关兜;若网关转换 tool_call id 有损,表现为回填 400 —— 失败降级路径(单步异常→文案回填→模型收尾)天然兜底,不会挂死。
- **回滚**:`tool_loop.enabled: false` 即完全回到现状(所有分支都在 active 判断之后)。

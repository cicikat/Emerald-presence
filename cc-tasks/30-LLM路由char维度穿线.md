# Brief 30 · LLM 路由的 char 维度穿线(多角色/群聊地基)

> 问题:preset 路由解析(Brief 29 · 3.2)依赖**全局活跃角色**,`llm_client.chat()` 全链
> 无 char 参数。单人切卡场景正确;多角色场景(Stage 群聊、日记白名单多角色生成、未来
> 任何"非活跃角色开口")会**错用活跃角色的路由**。趁调用点少,现在穿线。
>
> 原则:纯参数穿线,**默认行为零变化**——`char_id=None` 意为"按活跃角色解析",与现状
> 完全一致;只有明确知道"这次调用是替某个角色说话"的调用方才显式传。

---

## 1. 现状盘点(已确认)

| 事实 | 位置 |
|---|---|
| 路由解析:`_resolve_active_profile()` 读活跃角色卡 `presence_ext.model_routing`,回落全局 `active_routing` | `core/model_registry.py:152-171` |
| `get_model_client(call_category)` 无 char 维度 | `core/model_registry.py:215` |
| `llm_client.chat / chat_stream / chat_turn` 均无 char 参数 | `core/llm_client.py` |
| Stage runner 通过注入的 `generate_reply(stage, speaker_id, transcript, ...)` 回调生成回复,speaker 已知但没传到 LLM 层 | `core/stage/runner.py:31-114` |
| **现存 bug**:日记白名单多角色生成 `_generate_and_store_diary(oid, char_id)` 内部两次 `llm_client.chat(...)` 不带 char → 非活跃角色的日记用活跃角色的路由与语言风格参数 | `core/scheduler/triggers/time_based.py:456` |

## 2. 方案

### 2.1 model_registry

```python
def get_model_client(call_category: str, *, char_id: str | None = None) -> ModelClient
```

- `char_id=None` → 现行为(活跃角色卡 override → 全局 active_routing)。
- `char_id` 给定 → 读**该角色**卡的 `presence_ext.model_routing`(`character_loader.load(char_id)`,fail-soft),不存在/无字段 → 全局 active_routing。
- ModelClient 缓存已按 preset 名 key(cc 核对;若按 category key 则改为按 preset 名),多角色多 client 天然并存,无需新缓存层。

### 2.2 llm_client

`chat / chat_stream / chat_turn` 增加 keyword-only `char_id: str | None = None`,
只透传给 `get_model_client`。旧调用全部兼容,不改一处既有调用点的必填签名。

### 2.3 需要显式传的调用方(本 brief 全部接上)

1. **日记生成**:`_generate_and_store_diary` 内两次 chat 传 `char_id=char_id`(修 §1 现存 bug)。
2. **Stage**:`generate_reply` 的实际实现(cc 找到注入处,顺 `docs/stage.md`)把 `speaker_id` 对应的 char_id 一路传到 chat。若当前实现直接复用 owner pipeline,则 pipeline 侧加可选 `char_id` 透传(`run_llm/run_llm_stream/run_agentic_loop` 各加 keyword-only 参数,默认 None)。
3. **`run_agentic_loop`**(Brief 28):签名里已有 char_id,内部 `chat_turn` 调用补透传。
4. 其余(探针/summary/consolidation/杂活):**不传**,维持活跃角色语义——它们服务于当前会话,现状正确。

### 2.4 明确不做

- 不做 per-speaker 的 tool loop / 工具暴露面穿线(群聊本就不进 loop,Brief 28 §1)。
- 不改 routing 解析优先级、不加新配置项。
- 不动 vision(独立 client,无路由)。

## 3. 测试

`tests/test_char_routing.py`:

1. `char_id=None` → 与现行为逐字节一致(活跃角色 override 生效)。
2. 显式 `char_id=X`(X 卡带 model_routing=claude-main)且活跃角色是 Y → 解析用 X 的 profile。
3. X 卡无 presence_ext → 回落全局 active_routing(不是 Y 的 override)。
4. 日记多角色:白名单两个角色、卡路由不同 → 两次生成各用各的 preset(mock get_model_client 断言入参)。
5. 缓存:两个 preset 交替解析,client 实例各自稳定复用、互不串。

## 4. 风险

- 几乎为零:全部 keyword-only 默认 None,不传即现状。唯一行为变化是 §1 那个 bug 被修正(非活跃角色日记改用自己的路由)——这是修复不是回归。
- 费用注意:Stage 接线后,群聊里每个角色按自己卡的 profile 计费,卡里指了贵模型的角色开口就是贵模型的价格。

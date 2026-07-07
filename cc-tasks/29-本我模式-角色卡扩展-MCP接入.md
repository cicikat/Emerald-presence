# Brief 29 · "本我"模式:角色卡 per-char 扩展 + MCP 工具接入

> 依赖:Brief 28(tool loop)已合并。无前端配对文档——切换入口复用现有角色卡切换
> (chat 界面偏好→世界),per-char 字段 v1 手改卡 JSON,前端零改动。
>
> 定位:**"AI 本我"不是新模式,是一张极简角色卡 + 四个 per-char 兼容钩子 + MCP 客户端。**
> 整条 pipeline(记忆五层、固化、action_trace、tool loop)原样复用,本我作为独立 char_id
> 自动获得隔离的记忆桶(S6 布局 `memory/{char_id}/{uid}/`)。**不接外部 MCP 记忆库**:
> 外接记忆绕过 prompt 层注入与固化链,会裂成两套真相;MCP 只用于外部工具。

---

## 1. 现状盘点(已确认)

| 事实 | 位置 |
|---|---|
| 角色卡为 JSON(`characters/*.json`),`character_loader.load(char_id)`,已有 personality/mes_example 等字段被消费 | `core/character_loader.py`;`time_based._collect_diary_voice` |
| 消融开关是**全局**文件,build 后按 `_layer` 过滤注入、不短路检索,热生效,fail-open;`ALWAYS_ON={1_system_prompt, 12_user_message}` 不可消融 | `core/prompt_ablation.py`(任务23·B) |
| 破限注入是全局的(stems + `characters/reality/jailbreak_entries.json`),按 layer 0/2/11 注入,**不跟角色走** | `core/prompt_builder.py:219 _load_jailbreak` |
| routing 是全局的:`model_presets.active_routing` → profile → category → preset,无 char 维度 | `core/model_registry.py:160` |
| scheduler 主动发言种子为固定浪漫腔文案("深夜,他回想起…"),按 `_active_char_id_or_none()` 取活跃角色但**文案不区分角色类型** | `core/scheduler/triggers/*.py` |
| tool loop 暴露面是全局 config(`tool_loop.categories/exclude_tools`,Brief 28)| `config.yaml` |

## 2. 角色卡扩展字段 `presence_ext`

卡 JSON 顶层新增可选块(缺失 = 全默认 = 现有角色零行为变化):

```json
"presence_ext": {
  "disabled_layers": ["0_jailbreak", "2_jailbreak", "11_jailbreak", "..."],
  "model_routing": "claude-main",
  "tool_categories": ["info", "desktop", "memory", "mcp"],
  "proactive": "off"
}
```

- `character_loader` 解析并暴露(getattr 风格,与现有字段一致,全 fail-soft)。
- 层名以 `docs/prompt-layers.md` 现表为准;cc 执行时核对破限第三个注入点的真实 `_layer` 名(11 层那支)。
- 随文档附一张**本我示例卡** `characters/benwo.example.json`:极简 description(百字级)、无 lorebook、`disabled_layers` 关掉破限/author_note 轮换/花园/关系层(具体层名 cc 对表)、`proactive: "off"`、`model_routing` 指向 FC 能力强的 preset、`tool_categories` 含 `mcp`。命名遵守硬性规则8(示例卡内容不写死现有角色名)。

## 3. 四个 per-char 兼容钩子

### 3.1 注入过滤(复用消融机制)

`prompt_ablation.get_state()` 增加合并逻辑:全局 disabled_layers ∪ 活跃角色卡的
`presence_ext.disabled_layers`。`ALWAYS_ON` 白名单照旧不可消融。
活跃角色的获取复用现有 active char 通道(admin/routers/character.py 那套),进程内缓存
跟随角色切换失效。全局消融文件语义不变(管理面板那页不受影响)。

### 3.2 routing override

`model_registry` 路由解析第一步改为:活跃角色卡有 `presence_ext.model_routing` 且该
profile 存在 → 用它;否则回落全局 `active_routing`。profile 不存在时 log warning +
回落,fail-open。ModelClient 缓存 key 需含 profile 名(避免切角色后拿到旧 client)。
**注意**:probe/summary/consolidation 等杂活类别也会随 profile 走——这是预期(本我
的 profile 里自己声明杂活给谁,参照 docs/model-presets.md 的 claude-main 样例)。

### 3.3 scheduler 发言闸门

`presence_ext.proactive`:`"full"`(默认,现状)/ `"off"`。
判定点放**发言收口**而非各 trigger:`gating._decide` 入口与 `legacy_tick_should_send`
各加一道"活跃角色 proactive=off → 拒绝所有发言类 proposal/legacy 发送"。
**维护任务不受影响**(episodic_decay、inner_diary_write(Brief 26)、diary_inject、
hidden_state_decay、garden 自动浇水等不发言任务照跑)。
v1 不做 `"minimal"` 档(reminders 也压掉;真有需要下个 brief 再分级)。

### 3.4 per-char 工具暴露面

Brief 28 的 `run_agentic_loop` 取 categories 时:活跃角色卡有 `presence_ext.tool_categories`
→ 用它,否则全局 `tool_loop.categories`。`exclude_tools` 仍然全局(硬件排除不许 per-char 绕过)。

## 4. MCP 客户端(核心新件)

### 4.1 配置

```yaml
mcp_servers:
  enabled: false
  servers:
    - name: filesystem
      transport: stdio            # stdio | http(streamable)
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "D:/some/dir"]
      # http 时: url: https://...
      tool_timeout_s: 30
      allow_tools: []             # 空 = 全部;非空 = 白名单
```

依赖:官方 `mcp` Python SDK(requirements.txt 加锁版本)。

### 4.2 生命周期:`core/mcp_client.py`(新文件)

- 启动时(main.py 与 run_test 的既有初始化位)对每个 server 建立 session,`list_tools`,
  失败单 server 隔离(log + 跳过,不影响其他 server 与主流程)。
- 工具注册:转成 `_TOOL_REGISTRY` 动态条目,`name = "mcp__{server}__{tool}"`,
  `category = "mcp"`,description/inputSchema 直接映射为 OpenAI function schema。
  与静态注册表同名冲突时 MCP 侧让位 + warning。
- 执行适配:`execute()` 分发到 `session.call_tool`,超时 `tool_timeout_s`,结果取文本
  content 拼接、截断 2000 字;异常 → 返回失败文案(loop 的单步失败语义,Brief 28 §3.2)。
  **action_trace 自动生效**(收口埋点在 execute,零新代码);MCP 工具默认不进
  `trace_args` 白名单(参数不落痕,防外部 server 的敏感入参入盘)。
- 断线:调用时 session 已死 → 尝试重连一次,再失败按工具执行失败处理。不做后台心跳。
- 探针不覆盖 mcp 类(探针 prompt 只拼 info/desktop,现状不动):**MCP 工具只经 tool loop
  暴露**——这就是"本我接 MCP、角色扮演不受影响"的实现方式:角色卡 `tool_categories`
  不含 `"mcp"` 就永远看不见这些工具。

### 4.3 provider 细分说明(拍板:不细分)

DS/Claude/GPT 在代码层无分支:全部经 OpenAI-compat 网关走 function calling
(Brief 28 已验),参数差异由 provider_kind 白名单处理,MCP 工具 schema 是标准
JSON Schema 直转。唯一不覆盖的场景是**原生 Anthropic API 直连**(非网关),当前
架构全走网关,维持现状,不为此加适配层。

## 5. Brief 28 补丁:工具意愿软提示(顺手修)

观察:长上下文 + 弱代理模型时 loop 几乎不主动调工具。便宜缓解:

- `tool_loop.nudge_hint: true`(默认 true)时,loop 首步在 messages **尾部、用户消息之前**
  注入一条 system:"需要外部信息或操作时,直接调用可用工具,不要凭记忆编造。"
  (利用 recency 位置;≤50字;带 `_layer: "11.5_tool_nudge"` 并登记层表。)
- 仅 loop 激活轮注入,一次性,不进 history。
- 观察手段:action_trace 里 origin=assistant_loop 的条数就是调用率指标,不另做统计。

## 6. 文档同步

- `docs/tools.md`:MCP 一节(注册命名、超时、痕迹脱敏、"只经 loop 暴露")。
- `docs/model-presets.md`:per-char `model_routing` 覆盖规则。
- `docs/prompt-layers.md`:per-char disabled_layers 合并语义 + `11.5_tool_nudge` 层。
- `docs/scheduler.md`:`proactive: off` 闸门(维护任务不受影响清单)。
- `AGENTS.md` 速查表:`core/mcp_client.py`。

## 7. 测试

1. `presence_ext` 缺失 → 四个钩子全走默认,现有角色回归零变化(重点回归)。
2. 注入合并:卡关 `2_jailbreak` → build 产物无该层;`1_system_prompt` 写进卡的 disabled_layers 也不掉(ALWAYS_ON)。
3. routing:卡指向存在的 profile → chat 类别路由到对应 preset;不存在 → 回落 + warning;切角色后缓存刷新。
4. proactive=off:gating 全拒发言 proposal;`inner_diary_write`/`episodic_decay` 照跑。
5. MCP:mock server(SDK 自带测试设施或 stub session)→ list_tools 注册、命名前缀、同名让位、call_tool 超时→失败文案、断线重连一次、action_trace 落痕且 args_digest 为空。
6. 暴露面:卡 tool_categories 无 "mcp" → loop schema 不含 MCP 工具;有 → 含;exclude_tools 全局仍生效。
7. nudge:loop 首步注入、非 loop 轮不注入、开关可关。

## 8. 风险与不做什么

- **风险**:MCP server 是外部进程,工具描述/结果是不可信输入——结果截断 + 参数不落痕
  之外,v1 不做内容级过滤,known-issues 登记"MCP 结果可能含注入性文本"待后续
  (与 web_search 结果同级风险,现状已接受)。
- **风险**:routing 随角色切换,费用随之切换——本我挂 Claude 时闲聊也是 Claude 价格,
  卡里自己配杂活类别回落便宜 preset。
- 不做:前端任何改动;`proactive: minimal` 分级;MCP resources/prompts(只接 tools);
  原生 Anthropic 直连;跨角色共享记忆;探针覆盖 mcp 类。

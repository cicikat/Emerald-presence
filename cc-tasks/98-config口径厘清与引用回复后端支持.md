# Brief 98 · config 双文件口径厘清 + 引用回复(reply_to)后端支持

> 背景:release 包真机复测(20260718)。§1 独立;§2 是 desktop Brief 36 与
> mobile Brief 09 §4 回复功能的前置。两节可并行施工。

## 1. 🟡 config.yaml 与 config.example.yaml 口径厘清

- 结论先行(已核实,写进文档即可):**config.yaml 是唯一生效配置,管理面板
  读写的就是它**;example 只是首次安装的复制源。config.yaml 更长、无注释是
  面板写回展开默认值 + YAML dump 剥注释的预期结果,不是坏文件。
- 施工项:
  - 跑 `scripts/gen_config_example.py` 重新对齐 example 与实盘键集合;
    对齐后**逐键审查**:凡代码中已无读取方的死键(历史遗留),从生成结果、
    example、以及面板写回的默认展开中一并剔除(先 grep 读取方确认再删,
    列清单进执行记录)。
  - example 的分组注释补到覆盖全部现存键(现有注释质量保持,新键补注释)。
  - README / example 头部加三行说明:「config.yaml 为程序管理,注释会被
    写回剥离属正常;字段含义查 config.example.yaml;两文件键集合由
    gen_config_example.py 保持同步」。
  - 面板写回顺手核实:写回是否保序(键序大幅乱跳会让手工 diff 困难,若现状
    乱序,dump 时按 example 键序输出,低成本能做就做,不能做不阻塞)。

## 2. 🟡 引用回复(reply_to)支持

- 契约(desktop / mobile 共用,加在现有聊天入口的请求体,可选字段):
  ```
  reply_to: {
    text: string,      # 被回复的角色气泡原文(客户端截断至 ~200 字)
    ts: float,         # 该气泡消息的时间戳
  }
  ```
  不建消息 ID 体系,v0.1 就用文本+时间戳,够用且零迁移。
- 处理:`build_prompt()` 阶段,最新一条用户消息前拼前缀:
  「用户回复了你{相对时间}发送的这条消息「{text}」:」——相对时间格式化
  规则:当天 →「今天 HH:MM」;1–6 天 →「N 天前」;更早 →「M月D日」。
  实现为独立小函数并配单测。
- 前缀作为用户消息内容的一部分进入 pipeline,因此 short_term / mid_term /
  event_log 自然捕获,无需额外记忆改造;但要核实
  `_sanitize_assistant_message()` 不受影响(前缀在 user 侧,理论无关,
  过一眼即可,Hard Rule 5)。
- 校验:text 超长截断、ts 非法(未来时间/负数)时忽略 reply_to 降级为普通
  消息,不报错;prompt 层如新增独立层需带 `_layer`(Hard Rule 3),
  但**推荐直接拼进用户消息**,不新增层,躲开 pruning 交互。
- `docs/backend-integration.md` 补契约,desktop Brief 36 / mobile Brief 09
  按此实现。

## 验收

- §1:gen 脚本产物与 example 键集合一致;死键清单落执行记录;fresh 安装 +
  面板改一项配置后,config.yaml 可正常重载、无未知键警告。
- §2:带 reply_to 的请求,prompt 中出现正确前缀与相对时间(单测覆盖三种
  时间档);不带 reply_to 的请求零回归;非法 reply_to 静默降级。
- `pytest -n auto` smoke 通过。

## 执行记录（2026-07-19）

### §1 config 口径

- 跑 `scripts/gen_config_example.py` 时先发现一个真实脱敏漏洞：`mail.smtp_user` /
  `from_addr` / `to_addr` 未命中 `SENSITIVE_KEY` 正则，真实 Gmail 地址原样进了生成产物；
  脚本自带的 leak self-check 只匹配字面量 `"@gmail"`，不通用也不阻断。已修：新增
  `EMAIL_RE` 通用邮箱识别（不依赖具体域名）在 `redact()` 里兜底替换为
  `YOUR-EMAIL@example.com`；self-check 改为扫描全部邮箱匹配并排除
  `example.com` 占位值，同时给出可读的泄漏类型而非裸正则。产物
  `config.yaml.example.generated` 补进 `.gitignore`（脚本文档本身就注明这是
  人工审查中间产物，不应入库）。
- 用 Python 展开 `config.yaml` 与 `config.example.yaml` 的完整点路径键集合做 diff：
  - **实盘有、example 没有**：只有 `embodiment.heart.{enabled,cooldown_sec,duration_ms}`
    一项。grep 确认 `core/embodiment/heart.py::maybe_draw_heart()` 读取该块（爱意探针
    命中后请求板子画爱心），确属遗漏的真实键，已按现有分组风格补进
    `config.example.yaml`（hardware 块之后）并加注释。
  - **example 有、实盘没有**（约 50 个点路径键，如 `dream.*` / `watch.fresh_days` /
    `screen_peek.*` / `presence.growth_activity_prob` / `pseudo_stream.*` /
    `private_exchange.*` / `anniversaries` / `group_chat.{speak,react}_threshold` 等
    Brief 84/85/86/88 功能键、`anti_collapse.{hint_rounds,segment_min_len,
    segment_recent_n}`、`memory.group_context_{keep_latest,min_score,top_k}`、
    `tool_loop.nudge_hint`、`scheduler.max_daily_proactive`、
    `web_autosearch.min_interval_min`、`mcp_servers.servers`、
    `tools.peek_screen_content`、`performance_mapping.{provider,llm_timeout_sec}`）：
    逐键 grep 读取方，**全部确认仍有活跃读取代码**——这些只是当前这份实盘部署没有
    显式覆盖、走代码内默认值的可选功能开关，不是"代码里已无读取方"的历史死键。
    结论：**本轮死键清单为空**，一个都没删。
  - 唯一的边界案例：`stage.idle_theater` 全仓 grep 零命中读取方，但它是 Brief 85 里
    明确标注"后台自发群聊/小剧场——默认关闭，未实现，未来若开必须走
    ProactiveLedger"的**前瞻占位符**，不是"历史遗留的死键"（工单定义的删除对象），
    保留不动。
  - `tools.peek_screen_content` 一度怀疑是死键（真正的 enable gate 是
    `screen_peek.enabled`，见 `core/tools/screen_peek.py`），但 grep 到
    `core/tool_dispatcher.py::_is_tool_enabled()` 会通用地读 `tools.<tool_name>`
    做工具暴露开关，`peek_screen_content` 走的正是这条通用路径，确认非死键。
- 面板写回保序核实：全仓 20+ 处 `admin/routers/*.py` 写回都已经是
  `yaml.dump(full_cfg, ..., sort_keys=False)`，且 `full_cfg` 来自
  `yaml.safe_load()`（Python dict 天然保留文件读入顺序）——写回本就保序，
  不存在"键序大幅乱跳"，此项无需改动。
- `config.example.yaml` 头部、`README.md` "Configure" 节各补了口径说明
  （config.yaml 是唯一生效配置；注释被写回剥离属正常；字段含义查 example；
  两文件键集合靠 `scripts/gen_config_example.py` 同步）。

### §2 reply_to

- 新增 `core/reply_context.py`：`format_relative_time()`（今天 HH:MM / N天前 /
  M月D日 三档，按自然日边界而非 24h 滚动窗口判定）+ `build_reply_prefix()`
  （校验 + 拼前缀，非法输入返回 None）+ `apply_reply_prefix()`（薄封装，非法/
  缺失时原样返回 message）。允许 5 秒时钟误差容忍未来时间，避免真实场景下的
  客户端/服务端时钟抖动被误判为"未来消息"而整体降级。
- 接入点：`admin/routers/chat.py`。`/desktop/chat` 请求体新增可选 `reply_to`
  字段；`run_owner_chat_turn()` 加 `reply_to` 形参，在**探针文本捕获之后、
  conversation_lock 之前**对 `message` 做一次性前缀拼接——之后 `fetch_context` /
  `build_prompt` / `record_assistant_turn(user_text=message)` 全部消费同一个
  拼接后的字符串，所以 short_term/mid_term/event_log 走原有 capture_turn 链路
  自然捕获前缀，未新增记忆写入点，未新增 prompt 层。
- 探针隔离：`_probe_text` 在前缀拼接**之前**求值，故显式使用拼接前的原始文本，
  避免被引用原文里的操作性短语（如引用了一条含"打开音乐"的历史消息）误判为
  当轮工具调用指令。
- 追加验证（Hard Rule 5 + 防串听）：
  - `core/memory/short_term.py::_sanitize_assistant_message()` 全仓 3 处调用点
    （`short_term.py`/`tool_dispatcher.py`/`stage/context.py`）均只处理
    assistant 角色内容，不受用户侧前缀影响。
  - `core/turn_sink.py::_fanout()` 只广播 `assistant_text`，从不广播
    `user_text`/`memory_input`——引用前缀不会被回显进其他设备的聊天 UI。
- mobile 接线：本仓目前没有独立的 mobile 聊天发送端点（`/mobile/*` 只有
  activate/deactivate/poll/ack/push，push 是服务端→客户端方向），
  `run_owner_chat_turn(reply_to=...)` 的 channel 参数本就是通用的，mobile
  Brief 09 落地自己的发送入口后直接透传 `reply_to` 即可，无需再改本仓。
- 新建 `docs/backend-integration.md`（本仓此前没有这份契约文档）承接 reply_to
  的跨仓字段契约，从 `docs/README.md` 与 `docs/api-reference.md` 各链接一处。
- 单测：`tests/test_reply_context.py`，16 例，覆盖三档相对时间边界（含
  恰好 7 天的边界值）、`reply_to` 非 dict / text 空 / ts 负数 / ts 未来 /
  ts 非数字 / ts 为 bool（`isinstance(True, int)` 陷阱专项）、超长文本截断到
  200 字、`apply_reply_prefix` 缺失/非法透传原文。

### 验收结果

- `pytest -n auto`（全量 4971 用例）：4971 passed，2 failed + 1 error。失败项
  为 `tests/test_r4_prompt_layer_boundary.py::TestLLMBoundaryStrip` 两例与
  `tests/memeval/test_memeval.py` 一例，报错均为
  `openai.BadRequestError: messages: at least one message is required`
  （真实网络/LLM 网关调用失败）。用 `git stash` 回退到本单改动之前重跑同两个
  文件，失败现象与报错一致——确认是与本单改动无关的既存问题，未顺手修复
  （AGENTS.md「只改任务相关文件」约定）。
- `tests/test_reply_context.py` 16/16 通过；`/desktop/chat` 链路相关既有
  回归测试（`test_sec_auth1/2`、`test_reality_output_guard`、
  `test_perceive_event`、`test_dream_turn_isolation` 等 11 个文件 267 例）全绿。

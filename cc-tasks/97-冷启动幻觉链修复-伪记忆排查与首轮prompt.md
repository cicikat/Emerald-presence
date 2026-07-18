# Brief 97 · 冷启动幻觉链修复:伪 mid-term 排查 + 触发器门控 + 首轮专用 prompt + 关系层冷启动

> 背景:release 包真机首启实测(20260718)。全新用户第一轮对话就出现:
> 角色主动说「你好久没写日记了」,mid-term 里凭空出现「她收到日记分析提醒并
> 回复了近况」——完全没发生过。这是一条冷启动幻觉链,本单先诊断后修复。
> 与 desktop 仓 Brief 35 可并行,无相互依赖。

## 1. 🔴 诊断:伪 mid-term 从哪来(先查清再动手,写结论进执行记录)

复现路径:全新 data/ + 只填聊天 API 和 owner_id → 首次打开 desktop。排查顺序:

- 首启到底触发了哪个 scheduler trigger?预期是「desktop 打开」类事件,实际
  疑似 `core/scheduler/triggers/diary.py`(全新安装「上次写日记时间」为空 →
  被判定为「很久没写」)。查 `core/scheduler/loop.py` 触发日志确认。
- 伪 mid-term 生成机制:主动触发的那一轮走 pipeline 后,post_process 的
  mid-term 压缩把**触发器种子指令**(「日记分析提醒」之类的 system 侧文案)
  当成了真实发生的对话去概括?核对 `capture_turn → mid_term` 链路里,
  scheduler 主动轮的输入是以什么角色/内容进入压缩 prompt 的。
- 结论必须回答:①哪个 trigger 在零数据时误触发;②种子指令为何进入了记忆
  压缩的视野。

## 2. 🔴 修复 A:触发器冷启动门控

- 依赖「历史交互存在」的触发器(diary、festival 问候、interest_seed 等,
  逐个过 `core/scheduler/triggers/`)统一加冷启动门控:该 uid 的真实对话
  轮数 < N(建议 N=5,常量集中定义)或 memory 文件不存在时,直接 skip 并
  记 debug 日志。「久未见/久未写」类判断,把「从未有过记录」和「有记录但
  很久没更新」区分开——前者一律不触发。

## 3. 🔴 修复 B:记忆压缩隔离触发器指令

- mid-term / event_log 的 capture 输入里,scheduler 种子指令(非用户消息、
  非角色最终回复的中间指令文本)不得作为「已发生的事」参与概括。按 §1 查明
  的实际泄漏点修:要么 capture 时过滤掉种子层,要么压缩 prompt 明示
  「以下 system 指令不是已发生事件」。修改涉及 assistant 消息写入逻辑时,
  先读 `core/memory/short_term.py` 的 `_sanitize_assistant_message()`
  (Hard Rule 5)。

## 4. 🟡 修复 C:首轮专用种子 prompt

- 现状:desktop 打开事件的种子是「用户重新打开了和你对话的软件,请结合真实
  记忆……」——零记忆时等于点名要求编造。
- 判定条件:该 uid 无 history/episodic/identity 文件(或真实轮数为 0)时,
  换用首见版种子,文案基调(可润色):「用户第一次打开和你对话的软件。
  说出你想说的话吧:打个招呼,礼貌地询问,或者随便说几句。不要假装拥有
  与用户过去的记忆。」最后一句防幻觉约束必须保留。
- 非首次仍走现有种子。新 prompt 层若新增,带 `_layer` 字段(Hard Rule 3);
  改动后跑 `python tests/run_eval.py`(如涉 tag_rules)。

## 5. 🟡 修复 D:关系层冷启动(已代拍板,理由如下)

- 现状:prompt 有 `<与用户关系>` 层,零数据默认 `stranger`;编辑入口只在
  用户管理页,角色卡页没有。
- **拍板:不做全局消融,也不在角色卡页加编辑框**。理由:关系是
  (角色×用户) 维度的运行时状态,塞进角色卡(纯角色维度)会造成两处真源;
  而整层消融会把长期玩下来的关系演进一起砍掉,因小失大。
- 实际修复:关系数据**不存在/仍为初始默认值**时,该层整体不注入
  (没有信息就别说,胜过注入「陌生人」误导角色对 owner 冷淡);有真实
  关系数据后照常注入。层的 drop/注入逻辑遵守 `_drop_priority` 既有机制。
- 辅助:角色卡页加一行只读提示 +「去用户管理页编辑关系」跳转链接,解决
  「找不到在哪改」;用户管理页关系编辑功能保持现状不动。

## 6. 🟢 429 日志降噪(后端侧,配合 desktop Brief 35 的指数退避)

- 同一来源短时间内重复的 401/429,日志聚合为「N 次重复,已抑制」级别输出,
  不再逐条刷屏;首条保留完整信息。限流本身的阈值不动。

## 验收

- 全新 data/ 首启:角色打招呼式开场,不提日记/不编造往事;mid-term 首轮
  产物只含真实发生的内容;诊断结论写入本单执行记录。
- 老用户数据(有历史)回归:diary 等触发器照常工作,关系层照常注入。
- `pytest -n auto` smoke 通过;新增门控有对应测试(零数据 skip、有数据触发)。

## 执行记录（2026-07-18）

### §1 诊断结论

复现路径：全新 `data/` + 只填聊天 API 和 `owner_id` → 首次打开 desktop。

**① 哪个 trigger 在零数据时误触发**：不止一个，两条独立链路都会命中：

1. `core/scheduler/triggers/diary.py::_check_diary_reminder` /
   `propose_diary_reminder`：门控依赖 `core.tools.diary_reader.yesterday_missing()`，
   该函数只判断"昨天那天有没有日记文件"，从未写过日记与"昨天恰好没写"在这里是
   同一个返回值（`True`）——冷启动时诊断已确认走的是这条（提醒文案正是
   "你翻到了{yesterday}的日期，她好像漏了一天没写"）。
2. `_check_diary_share_reminder` / `propose_diary_share_reminder`：门控依赖
   `_last_diary_share`，全新安装恒为 `0`；`time.time() - 0` 恒大于三天阈值，
   "从未分享过"被判定成"分享过但已经好几天没看到"，文案是
   "你发现自己好几天没看到她写的东西了"。
3. （非 trigger 误触发，但同因同果）`admin/routers/chat.py::desktop_wake` Path B
   的种子 prompt 本身写死"请结合真实记忆自然接续"——零记忆时这句话等于点名
   要求角色编造往事，是 §4 的直接成因。

`quiet_floor_elapsed()`（`core/scheduler/rhythm.py`）同样是"从未对话”时返回
`True`（elapsed），但它只表达"当前允许开口"，不单独构成假记忆；真正编造内容的是
上面两个日记判定函数把"没有数据"读成了"有数据但很久没更新"。

**② 种子指令为何进入了记忆压缩的视野**：`core/pipeline.py::post_process_slow()`
把触发器的 `content`（即括号旁白原文，例如"你翻到了…她好像漏了一天没写"）原样
写进 `_mt_payload["user_content"]`，入队 `summarize_to_midterm`；
`core/memory/fixation_pipeline.py::summarize_to_midterm()` 再原样转给
`llm_client.summarize_turn(user_msg=..., reply=...)`。`summarize_turn` 此前不区分
调用方是真实用户轮还是触发轮，一律用 `_SUMMARIZE_SYSTEM`（"主语用「用户」，只描述
发生了什么"）压缩，于是 LLM 把旁白当成"用户做了/说了什么"去概括，产出
"她收到日记分析提醒并回复了近况"这类凭空事件。`reflect_to_episodic` 早就用
`is_trigger_turn` 挡住了 trigger 轮进入 episodic（P0 trigger boundary，Brief 之前的
工作），但 mid_term 这一层此前没有同等隔离——伪记忆先污染的正是 mid_term，
这也解释了为什么诊断只在 mid_term 里看到，而没有污染 episodic/identity。

### 修复对应关系

| 编号 | 结论 | 修复 |
|---|---|---|
| ①-1 | `yesterday_missing()` 零数据误判 | `diary_reminder` 接入 `has_real_interaction_history` 冷启动门控 |
| ①-2 | `_last_diary_share=0` 零数据误判 | `diary_share_reminder` 接入同一门控，并把 `<=0`（从未分享）与"分享过但过期"拆开判断 |
| ①-3 | `desktop_wake` 种子邀请编造 | 真实轮数为 0 时换用首见版种子（§4） |
| ② | mid_term 压缩把旁白当事实 | `summarize_turn`/`_rule_fallback` 新增 `is_trigger_turn`，trigger 轮改用旁白专用系统 prompt + 消息框定（§3） |

### 范围裁剪说明（供复核）

- `festival`/`timenode`/`holiday_boost` **未接入冷启动门控**：三者只依赖真实日历
  日期 + `owner_id` 是否存在，不引用"距上次交互"的时间差，对全新用户不构成
  虚假共同历史（"今天是白色情人节"对谁都成立），排查后判定不属于本单症状。
- `overflow`/`letter_writer`/`presence_nag` 的"时间差"信号已经用
  `if timestamps:` / `last_owner_turn <= 0 → None` 等写法正确区分"没有数据"与
  "很久以前"，本就不受冷启动误判影响，未改动。
- `interest_seed` 功能上零数据时 `candidates` 为空、`choose_candidate` 本就返回
  `None`，不会实际误触发；仍按 brief 点名接入了同一门控，避免未来改动改坏这个
  隐性前提。

### §5 关系层：已按 brief 拍板落地

`core/user_relation.has_configured_relation(user_id)` 判断 `relations.yaml` 是否有
该用户专属条目或全局 `default` 段；`core/prompt_builder.py` 的 `3_relation` 层仅在
返回真时注入，冷启动/未配置时整层跳过（不写死 stranger）。角色卡编辑器页新增一行
只读提示 + 跳转到用户管理页的链接，用户管理页关系编辑功能不动。

### §6 429/401 日志降噪

`admin/log_filter.py` 新增 `SuppressRepeatedAuthFailureFilter`：同一来源 IP 60s 窗口内
重复的 401/429，首条完整放行，窗口内后续静默计数，窗口过期后下一条命中时改写为
"上一窗口内状态 N 重复，已抑制 M 次"再放行；限流阈值本身（`admin/auth.py`）不变。

### 测试

- 新增/更新：`tests/test_desktop_wake_origin.py`（新增冷启动首见种子用例）、
  `tests/test_log_filter.py`（`SuppressRepeatedAuthFailureFilter` 6 条用例）、
  `tests/test_rhythm.py` / `tests/test_execute_dryrun.py`（诊断门控生效后同步补
  `has_real_interaction_history` mock，`_last_diary_share` 测试夹具从 `0` 改为
  真实过期时间戳，避免继续断言旧的"零值当过期"行为）、
  `tests/test_slow_queue_char_scope.py` / `tests/test_memory_isolation_p0_final.py`
  （mock 的 `summarize_turn` 补 `**kwargs` 接住新增的 `is_trigger_turn`）。
- `pytest -n auto` 覆盖本单改动涉及的全部文件（scheduler/triggers、fixation_pipeline、
  llm_client、prompt_builder、user_relation、chat.py desktop_wake、log_filter）：
  全部通过。`tests/test_desktop_wake_origin.py` 单独/小批量运行时会撞上一个与本单
  无关的既有 flake（该文件的 `sys.modules["core.sandbox"]` stub 与 `conftest.py`
  的 `_default_sandbox_guard` autouse fixture 在某些 worker 分配下冲突，`git stash`
  验证 main 分支同样复现）——随大批量 `-n auto` 一起跑时不触发，不在本单范围内。

### 追加修复（用户复核发现的缺口，2026-07-18）

用户提问点出：`diary_reminder` 读的是用户真实日记目录（`config.diary.obsidian_path`
未配置时回落本地 `data/diary_fallback/`），而 §2 的冷启动门控只挡了"聊天轮数不够"
这一种零数据——一个已经正常聊了很久、但从没配置日记路径/从没写过一篇日记的老用户，
`yesterday_missing()` 依然永远返回 `True`，`diary_reminder` 会每天照样奇怪地触发。

修复：`core/tools/diary_reader.py` 新增 `has_any_diary_entry()`——判断日记目录里
是否曾经出现过至少一篇 `YYYY-MM-DD.md`（不限昨天/最近几天，目录不存在或为空一律
`False`）；`_check_diary_reminder()` / `propose_diary_reminder()` 在 `yesterday_missing()`
判断之前先查这个，从未有过任何一篇日记时直接 skip，不再要求用户"必须配置/写过
日记"才能免于被莫名提醒。新增 `tests/test_diary_reader_has_any_entry.py`（5 条用例）
+ `test_rhythm.py` 补的 `test_diary_reminder_propose_skips_when_diary_never_used`；
`pytest -n auto` 全量复跑通过（4947 passed，失败集与此前一致，均为无关 flake）。

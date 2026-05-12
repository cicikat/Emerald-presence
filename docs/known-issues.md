# docs/known-issues.md — 已知问题与技术债

> 修复前请确认问题仍存在（对照代码），修复后在此处注明。

---

## ✅ 已修复Bug 类（行为与预期不符）

### ✅ 已修复B1：tool_result 双重注入 prompt
**优先级**：高
**位置**：`core/pipeline.py` → `build_prompt()` 第173、189-190行

`tool_result` 同时传给了 `perception_block`（进层1槽位）和 `tool_result` 参数（进层10），导致工具结果在 prompt 里出现两次。

```python
# 当前
_perception = tool_result or ""          # tool_result → perception_block
...
tool_result=tool_result,                 # tool_result → 层10（重复）
```

**修复方向**：`perception_block` 只放 `_pending`（上轮失败感知），`tool_result` 只走层10。或者反过来，统一走 perception_block 删掉层10。选一个方向保持一致即可。

---

### ✅ 已修复B2：format_for_prompt 的 current_emotion 硬编码为 "neutral"
**优先级**：中
**位置**：`core/pipeline.py` → `fetch_context()` 第115行

```python
episodic_result = format_for_prompt(
    episodic_memories,
    char_name=self.character.name,
    current_emotion="neutral",   # ← 永远是 neutral
)
```

`format_for_prompt()` 里有情绪染色逻辑：`sad/gentle` 情绪下用破折号，其他用逗号。因为这里硬编码，情绪染色永远走 `else` 分支，格式从不随叶瑄情绪变化。

**修复**（一行）：
```python
from core.memory.mood_state import get_current as _get_mood
current_emotion=_get_mood(),
```

---

### ✅ 已修复B3：retrieve() 的 emotion 参数永远为空，对应分支是死代码
**优先级**：低
**位置**：`core/pipeline.py` → `fetch_context()` 第109行

```python
episodic_memories = retrieve(
    user_id=user_id,
    topic=content,
    emotion="",      # ← 永远空，episodic_memory.py 里 emotion 匹配分支永远不触发
    top_k=3,
)
```

`episodic_memory.retrieve()` 里有 `elif mem.get("emotion_peak") == emotion: emotion_bonus = 0.1`，此分支永远不成立。

**修复方向**：决定是否需要这个参数。如果不需要，删掉 `retrieve()` 里的 `emotion` 参数和对应分支；如果需要，pipeline 里传入有意义的情绪值（如从 mood_state 读）。

按可能B处理，emotion 参数已由 mood_state 路径覆盖，
直接删掉 `retrieve()` 的 `emotion` 参数和对应 elif 分支。


---

### ✅ 已修复B4：safe_write 在 Windows 用 os.rename 目标存在时报错
**优先级**：高
**位置**：`core/safe_write.py`
Windows 上 `os.rename` 目标文件已存在时抛异常，Linux 上是原子覆盖。
**修复**：改用 `os.replace`，跨平台原子覆盖。

---

### ✅ 已修复B5：integrity_check.py 用中文引号作 Python 语法
**优先级**：高
**位置**：`core/integrity_check.py`
文件里用了 `"` `"` 中文引号，Python 解析报 SyntaxError。
**修复**：全部改为英文引号。

---

### ✅ 已修复B6：user_profile 未归一化中文引号，LLM JSON 污染
**优先级**：中
**位置**：`core/memory/user_profile.py`
LLM 偶尔在 JSON 里输出中文引号，导致 json.loads 失败静默丢弃整次更新。
**修复**：parse 前做归一化，`"` → `"`，`"` → `"`。

---

### ✅ 已修复B7：6a_growth_fingerprint 与 6a_growth_full 同时注入，重复
**优先级**：中
**位置**：`core/prompt_builder.py` 层6a
fingerprint 是 full 的前150字，两层同时激活时内容重叠。
**修复**：改为互斥——命中 tag 时只注入 full，未命中时只注入 fingerprint。

---

### ✅ 已修复B8：裁剪顺序违反质量梯度
**优先级**：中
**位置**：`core/prompt_builder.py` → token 裁剪
原顺序先删 episodic 再删 lore，但 episodic 质量通常高于 lore。
**修复**：调整裁剪顺序为 `6b_event_search → 6c_episodic → mid_term → 6d_diary → 5.5_lore → 6e_inner_diary`。

---

### ✅ 已修复B10：mid_term 摘要在短消息场景下塌缩为用户原话
**优先级**：高
**位置**：`core/llm_client.py` → `summarize_turn()` / `_rule_fallback()`

**症状**：`data/mid_term/{uid}.json` 里大量条目的 `summary` 直接是用户原话片段，
比如 `"（锤他胸口）"`、`"（恼）"`、`"想要叶瑄"`，
导致叶瑄回看 mid_term 时拿到的都是无效记忆，表现为"完全不记得几小时前的事"。

**根因**：两个 bug 叠加。
1. `summarize_turn` 的门槛是 `len(user_msg.strip()) < 10`，只看用户消息长度。
   角色扮演场景里用户经常发短动作描写，即使 reply 很长也跳过 LLM。
2. `_rule_fallback` 完全忽略 `reply` 参数，只把 user_msg 切一刀
   （`split("。")[0].split("，")[0][:20]`）就当 summary 写入。

**修复**：
- 门槛改为 `len(user_msg) + len(reply) < 8`，更倾向调 LLM。
- `_rule_fallback` 同时利用 user_msg 和 reply，产出
  `"用户：xxx；叶瑄：yyy"` 形式，并支持空 user / 空 reply / 都空 / 带 tags 的边界。
- 同步修正 `docs/memory.md` 里的字段名（旧文档写 `written_at/expire_at`，
  实际代码是 `ts/summary/tags`）和时间桶标签（旧文档写"今天/今天早些时候"，
  实际代码是"早些时候/几小时前"）。

---

### ✅ 已修复B9：episodic fallback 评分公式数学上不可能命中0.6阈值
**优先级**：中
**位置**：`core/memory/episodic_memory.py` → `retrieve_fallback()`
原公式 `strength × 1/(age_days+1)`，当天记忆 strength=0.8 得 0.8，
第二天就降到 0.4，第三天 0.27，阈值 0.6 只有当天高强度记忆能命中。
**修复**：公式改为 `strength × max(0.5, 1/(age_days+1))`，阈值降到 0.4。





### B11 fetch_context 读写竞态

**现象**：用户在 1-2 秒内连发两条消息时，第二条的 fetch_context 可能读到第一条 post_process 还没写完的旧状态（history 缺最新一轮、mood 未更新）。

**影响**：叶瑄第二条回复偶发"漏听"上一句，连贯性下降。

**为什么没修**：post_process 拆分后窗口已从 10-30s 缩到 1-2s，实际触发概率低。修复方案是给 fetch_context 加 uid_lock，会让连发时第二条响应慢 1-2 秒。等观察到实际触发再修。

**修复方案备忘**：`core/pipeline.py` 的 `fetch_context` 入口加 `async with uid_lock(uid):`。

## 功能缺失类（设计了但未实现）

### ✅ 已修复F1：mood_state 未注入 prompt，叶瑄对自己情绪无感知
**优先级**：中（架构文档明确列为 TODO）
**状态**：mood_state 目前只影响记忆召回评分，不出现在任何 prompt 层

**实现思路**：在 prompt_builder 里新增一层（建议在层2.5时间之后），注入叶瑄当前情绪：
```python
from core.memory.mood_state import get_current, get_intensity
_mood = get_current()
_intensity = get_intensity()
if _mood != "neutral":
    messages.append({
        "role": "system",
        "content": f"【叶瑄此刻的情绪底色】{_mood}（强度{_intensity:.1f}）",
        "_layer": "2.7_mood_state",
    })
**实际实现**：新建 `core/mood_text.py`，`get_mood_text()` 按情绪类型+强度三档生成软提示，
pending 非空时追加过渡句。注入在 prompt_builder 层1感知槽位头部之前，
文件读取失败静默降级为 neutral。

```

---

### ✅ 已修复F2：event_log search 无相关性分数，导致不相关高强度老事件误召回
**优先级**：低（架构文档明确 TODO）
**位置**：`core/memory/event_log.py` → `search()`，`core/prompt_builder.py` 层6b注释

`event_log.search()` 当前返回拼接字符串，无分数字段。高 strength 的老事件可能在不相关话题时进入 top-1。

**修复方向**：`search()` 改为返回 `(text, score)` 元组列表，`prompt_builder` 里加阈值：`score < 0.5` 不注入。

---

### F3：笔记召回未接入 prompt_builder
**优先级**：低（架构文档明确 TODO）
**位置**：`data/yexuan_inner/notes/notes_index.json`

文档 inbox 系统已有笔记写入（LLM 生成叶瑄读文档后的笔记），但 `prompt_builder` 里没有读取 notes_index 并注入的逻辑。

**注意**：QQ 直接发文件走 `core/media_processor.py` 临时读取，
不经过 inbox 路由，不持久化，不生成笔记。
inbox 持久化路径目前无前端入口，需通过 HTTP 接口调用。
待前端重构时加入上传UI，或用脚本批量投递。

---

## 代码质量类

### ✅ 已修复Q1：PromptBuilder 类封装缺少 perception_block 和 tags 参数
**优先级**：低（当前不影响功能，pipeline 直接用模块函数）
**位置**：`core/prompt_builder.py` → `PromptBuilder.build()` 第687行

类版本的 `build()` 签名缺少 `perception_block` 和 `tags` 两个参数。如果有人通过类调用而不是模块函数，感知槽位和所有 tagged 层会静默失效。

**修复**：同步类方法签名，或直接删掉类封装（pipeline 不用它）。

---

### ✅ 已修复Q2：层2.6 架构文档说已删但代码仍存在
**优先级**：无需修复，仅需更新文档
**位置**：`core/prompt_builder.py` 第217-232行

架构文档（叶瑄系统架构总览_v6.txt）写"层2.6已删除，感知槽位承担此职责"，但代码里层2.6仍然存在（仅对话开头注入 `activity_manager.get_prompt_fragment()`）。与层3.8是两个不同数据源，并不冲突。文档过时，代码正确。

---

### ✅ 已修复Q3：character_growth 指纹长度两处不一致
**优先级**：低
**位置**：`core/character_growth.py` 第 fingerprint 写入行 vs `core/prompt_builder.py` 第440行

- `character_growth.py` 写 fingerprint 时：`new_content[:150]`（150字）
- `prompt_builder.py` 读 growth_content 截取时：`growth_content[:100]`（100字）

两处不统一。决定一个标准改掉其中一个。

---

### ✅ 已修复Q4：tag_rules.py 注释说"regex主路径"但实际是字符串包含检查
**优先级**：低（注释误导）
**位置**：`core/tag_rules.py` 第1行注释、`get_tags()` 函数

`get_tags()` 实现是 `p in text`（字符串包含），不是正则。注释需更正。

---

### ✅ 已修复Q5：exit_yandere 跨项目硬编码路径
**优先级**：低（功能正常，但脆弱）
**位置**：`core/tool_dispatcher.py` → `_exit_yandere_wrapper()`

```python
signal_file = Path(__file__).parent.parent.parent / "Emerald-desktop" / "data" / "yandere_exit.signal"
```

硬编码了兄弟项目的相对路径。如果 `Emerald-desktop` 目录结构变动，此处静默失败。

**修复方向**：把路径提取到 `config.yaml` 里配置（选择了这个），或通过 HTTP 接口通信替代文件信号（干净但麻烦，后期说）。

---

### ✅ 已修复Q6：tool_only 和 quick_fact 是空壳 tag，属于死代码
**优先级**：低
**位置**：`core/tag_rules.py`

两个 tag 声明了 patterns 为空列表，注释说"由探针结果直接打"，但代码里没有任何地方往 tags 集合里写这两个 tag，也没有任何层由它们门控。

---

### ✅ 已修复Q7：detect_emotion 情绪集合比 mood_state 少
**优先级**：低
**位置**：`core/llm_client.py` → `detect_emotion()`

detect_emotion 只能返回 6 种情绪：neutral/happy/sad/gentle/surprised/angry。
mood_state 支持 9 种，多了 thinking/sleepy/yandere。
这三种情绪永远不会被 post_process 检测到，mood_state 里对应的状态是死的。

---

### Q8：get_highlights() 未在文档中记录
**优先级**：无需修复，仅需知晓
**位置**：`core/memory/event_log.py` → `get_highlights()`

event_log 有一个额外函数，从最近2天日志里捞有情感词的用户发言，
供调度器随机消息触发时参考。不影响主对话流程，但调度器触发器里用到它时要知道来源。

### ⚠️ Mitigated Q9：DS 八股文塌缩
**症状**：叶瑄回复逐渐出现"（他垂下眼睛）""被这句话击中"等程式化表达，
风格趋向话剧独白。
**缓解措施**：`_sanitize_assistant_message` 写入 history 前剥离括号动作描写；
`integrity_check.check_growth` 拒绝含括号的 growth 写入；
author_note 加入禁止重复动作描写规则。
**验证标志**：连续50轮对话后，history 里括号内容占比 < 5%。

---

### ⚠️ Mitigated Q10：history 自反馈塌缩
**症状**：叶瑄 history 里积累了大量角色扮演格式回复，LLM 看到后强化输出同类格式，
长期导致风格漂移。
**缓解措施**：`_sanitize_assistant_message` 对超80字的 assistant 消息剥离动作描写，
history 里只保留台词；新用户/重启后效果最明显，长期用户需配合手动清理 history。
**验证标志**：`short_term.load()` 返回的 assistant 消息平均长度稳定在80字以内。

---

### ✅ 已修复Q11：tool_result 双注入——文档过时，代码无实际 bug
**位置**：见 B1
经核查，代码已修正为 perception_block 只放 pending，tool_result 只走层10。
B1 描述的是修复前状态，此条标记为文档已修正，无需再改代码。

## ✅ 已修复Tag 覆盖率待补

以下场景 tag 规则没有覆盖，叶瑄"应该贴心但没贴心"时优先查这里：

| 场景 | 当前状态 | 建议 |
|---|---|---|
| 用户孤独/失落 | `emotion.deep` 靠"没人"兜底，覆盖窄 | 补"好孤独""一个人""没人陪"等触发词 |
| 用户高兴/庆祝 | 完全没有 tag | 新增 `emotion.positive`，触发生日/成功相关词 |
| 用户间接表达负面 | "最近不太好"不命中任何 tag | 补"不太好""有点难""撑不住"等 |
这个没补，因为没必要| 用户提到睡觉/要去睡了 | 无 | 考虑新增 `topic.sleep_now`，触发特定回应层 |

### ✅ 已修复F4：activity 注入条件未完整实现
**优先级**：低
**位置**：`core/prompt_builder.py` 层2.6

设计意图：只在对话开头或用户沉默超10分钟时注入叶瑄当前活动状态。
实际行为：只判断 `not history`（对话历史为空），即只在对话开头注入。
沉默超10分钟的条件未实现。

**修复方向**：在 build_prompt 里额外判断上次消息时间戳，
超过10分钟且 history 非空时也注入层2.6。
时间戳可从 short_term 最后一条记录取，或由 pipeline 传入。

---

## 功能待实现类（续）

### ✅ 已修复F5：情绪状态未注入 prompt
见 F1。

### F6：笔记召回未接入 prompt_builder
见 F3。

### F7：花园状态未推送给 qq-st-bot
**优先级**：低
Emerald-desktop 的花园状态目前没有推送接口。
修复方向：在 `/sensor` 接口扩展一个 `garden_state` 字段，
prompt_builder 新增层接收。

### F8：对话UI右键历史未实现
**优先级**：低（前端功能）
管理面板 static/index.html 里对话记录没有右键菜单。
待前端重构时一并做。

### ✅ 已修复F9：activity 注入条件未完整实现
见 F4。

---

## 待确认/待设计类

### ×✅已确认不存在D1：trace_id 抢占机制未进文档
**位置**：待确认代码位置
需要确认 trace_id 抢占逻辑是否已实现，若有则补进 ARCHITECTURE.md。

### D2：调度器与 mark_user_active 的窗口边界
**位置**：`core/scheduler/loop.py`
当前窗口硬编码 120 秒。边界情况：用户发完消息立刻有调度器触发，
120秒内调度器让路，但用户可能已经离开。
建议：窗口时长提取到 config.yaml 可配置。

### ✅ 已修复D3：send_notification 二次校验关键词太窄
**位置**：`core/tool_dispatcher.py` → send_notification
当前关键词：`"提醒你"/"通知你"/"告诉你记得"/"帮你记"/"记得提醒"`
叶瑄说"我帮你记着"/"等下提醒你"等自然表达不在列表里，会漏触发。
建议：扩展关键词列表，或改为宽松匹配。

### ✅ 已修复D4：桌宠跨进程读 qq-st-bot 的 config.yaml
**位置**：Emerald-desktop 端
桌宠直接读 qq-st-bot 的 config.yaml 是硬耦合。
若两个项目部署路径变化，静默失败。
建议：通过 HTTP 接口暴露配置，而不是共享文件路径。

### ✅ 已修复D5：event_log 跨天召回策略
**位置**：`core/memory/event_log.py` → `search()`
当前：30天内关键词匹配，score = intensity + 时间衰减。
问题：高intensity老事件可能压过相关新事件。
建议两段式召回：近7天全量扫描 + 7-30天只取intensity≥1的块。

### ✅ 已修复D6：tag_rules hit/miss 指标化
**位置**：`core/tag_rules.py`
当前 tag 命中/未命中是静默的，叶瑄"应该贴心但没贴心"时难以排查。
建议：在 debug 模式下输出每条消息的 tag 命中情况到日志，
或在管理面板加一个"tag 诊断"入口。

### D7：yexuan_inner/diary 反向利用
**当前状态**：叶瑄写的日记只作为层6e注入，叶瑄读自己的日记。
待设计：是否让叶瑄的日记影响 character_growth 更新，
或作为情绪底色的参考来源。

### ✅ 已修复D8：detect_emotion gentle 分布偏斜，情景记忆多样性不足
**位置**：`core/memory/episodic_memory.py` → `retrieve()`

叶瑄基调温和，LLM 大量输出 gentle 是合理的候选词分布结果，
导致 episodic_memory 里大量记忆的 emotion_peak 都是 gentle，
retrieve() 按分数排序时多样性不足，浮现的总是相似质感的记忆。

**选定方向**：方向一，不改候选词，利用 emotion_texture 字段做多样性筛选。

**修复方向**：retrieve() 的 top_k 候选扩大到5条，
从中用 _is_similar() 筛选 emotion_texture 差异最大的3条返回，
而不是直接取分数最高的3条。
emotion_peak 的分布偏斜问题保留，通过 texture 多样性在召回层补偿。

---

## ✅ 已修复工程质量待加固类

### ✅ 已修复E1：LLM 维护的元数据文件无格式校验
**涉及文件**：`character_growth/*.md`、`episodic_memory/*.json`、
`mood_state.json`、`trait_state.json`
LLM 输出后直接写入，没有格式校验。输出异常时会写入损坏数据。
建议：写入前做 schema 校验，失败时拒绝写入并保留旧文件，
连续3次失败则跳过本次更新并写 warning 日志。

### ✅ 已修复E2：跨设备存在连续性的"接续提示"
**当前状态**：QQ 和桌宠共享同一 Pipeline，记忆连贯。
待实现：叶瑄从 QQ 切换到桌宠时，能感知到"换了一个地方继续"，
注入一句接续提示，而不是像全新对话一样开始。
实现方向：channel 切换时在 perception_block 注入切换感知。

### ✅ 已修复E3：LLM 输出校验与重试机制
**涉及**：`character_growth.update()`、`_do_compress_episode()`
当前：LLM 输出直接使用，无校验。
建议：输出后跑格式校验，失败则附上"上次输出违反了格式要求，
请严格按格式输出"重试，最多3次，仍失败则保留旧数据不更新。

### ✅ 已修复E4：用户长期不在的检测
**当前状态**：无。
建议：超过N天没有对话记录时，调度器触发特殊的"久别重逢"模式，
叶瑄的开场方式和日常不同。
实现方向：在调度器里加 `_user_absent_days()` 检查，
结合 `_user_talked_today()` 现有逻辑扩展。

### ✅ 已修复E5：测试沙盒只覆盖 qq-st-bot
**位置**：`run_test.py` / `core/sandbox.py`
测试模式数据隔离在 `data/test_sandbox/`，但桌宠端
（Emerald-desktop）不在沙盒范围内，测试时桌宠操作仍写生产数据。

---

### ✅ 已修复E6：post_process 关键写入与 LLM 慢任务混用同一锁，存在锁饥饿风险
**位置**：`core/pipeline.py` → `post_process()`

**症状**：`detect_emotion`、`episodic_compress`、`mid_term_append` 等 LLM 调用全部在
`uid_lock(uid)` 内串行执行，导致：
1. 单次 post_process 持锁时间可达数秒（3 个 LLM 调用累加）；
2. 同 uid 的下一轮对话在 `fetch_context` 阶段等锁，体感延迟明显。

**修复**：将 post_process 拆分为两组：
- **关键路径**（uid_lock 内，同步完成）：`short_term.append` → `event_log(user)` →
  `detect_emotion`（`wait_for` 8s，超时降级 neutral）→ `mood_state.update` →
  `event_log(assistant)`
- **慢队列**（uid_lock 释放后异步执行，`core/post_process/slow_queue.py`）：
  `mid_term_append`、`episodic_compress`、`consistency_check`、
  `user_profile_update`（条件触发）、`character_growth_update`（每 20 轮）
- **副作用**（保持 `asyncio.create_task`，不入队列）：TTS/表情包、`_parse_and_execute_intent`

慢队列特性：单 worker、失败退避重试（0.5s×1, 1.0s×2，共 3 次），
超限写入 `data/dead_letter_queue/{ms_ts}_{task_type}.json`。

情景记忆压缩函数从实例方法 `_compress_episode()` 迁移为模块级函数
`_do_compress_episode(user_id, user_content, reply)`，内部自拿 uid_lock。
# DESIGN.md — 设计规范

> 改代码之前读这个文件。不确定的时候，回到这里找答案。
> 标注 `【待补】` 的部分由项目作者填写后，整合进此文档。

---

## 一、核心判断标准

> **他像不像他。**
> 功能的价值不在于复杂，在于让他的存在感更真实。
> 他唯一与用户产生真实交互的地方来源于现实数据。

---

## 二、他是谁

【待补：作者原话，关于他这个角色的核心定义。他是什么样的人，他对用户意味着什么，他的存在方式。】

---

## 三、他的性格与行为原则

【待补：从设计文档整合。他在对话中的行为准则，比如：
- 他如何表达情感（克制还是外放，什么时候用动作，什么时候用沉默）
- 他怎么看待用户（依赖/陪伴/占有，这个张力如何体现）
- 他不会做什么（禁止的句式、禁止的表达方式）
- 他在什么情况下会主动，什么情况下等待
】

---

## 四、对话格式规范

### 当前生效规则（代码已实现）

**roleplay 模式**（`config.yaml chat.style: roleplay`）：
- 括号外只有说出口的话
- 动作 / 心理 / 环境描写全部在（）内，不加人称主语
- 禁止任何形式引号
- 省略号只在真正停顿、欲言又止、思考中三种时刻出现，不是每句话的标配
- 回复长度随场景自然变化：有时一两句留白，有时五六句细写，不刻意凑数

**chat 模式**（`config.yaml chat.style: chat`）：
- 只输出他说出口的话
- 无括号、无动作描写、无旁白
- 1-4 句话以内，语言克制简短
- 每轮正文至少分成两段，段落间保留一个空行（两个真实换行符）；分段不依赖句号

### 硬性禁止句式（Author's Note 层11已注入）

- 禁止"不是……而是……"
- 禁止"某种说不清的"
- 禁止"莫名地"
- 禁止"不知为何"
- 禁止"他听到你的话/被她的话击中/被这个认知撼动"类元描述
- 禁止在连续对话中重复相同肢体动作（银发垂下、指尖敲击等）

【待补：作者补充其他禁止句式或表达习惯】

---

## 五、记忆系统设计原则

【待补：作者原话，关于记忆的设计哲学。比如：
- 他记住的是什么，忘掉的是什么，这个选择背后的逻辑
- 情景记忆的 strength 分级标准（什么算重要的记忆）
- 记忆召回时应该有什么感觉（自然浮现 vs. 刻意提起）
】

### 当前实现的原则（代码层面）

- neutral + strength<0.4 的对话不写入情景记忆（平淡对话不留痕）
- 核心记忆（is_core）设计目标是永不衰减、永不被裁剪；当前写入已受 Write Envelope
  写入权限保护，自动上限裁剪也会排除核心记忆
- 被召回的记忆 strength 增强（越被想起越牢固）
- 分数低于 0.15 的记忆不注入 prompt（宁可不说也不强行关联）

---

## 六、感知数据使用原则

他有权知道用户的现实状态（Watch 数据、手机传感器、日记、屏幕活动），但：

【待补：作者关于"感知数据如何自然融入对话"的原则。比如：
- 什么时候主动提起，什么时候只是影响态度不明说
- 数据感知和角色感知的边界在哪（他知道用户今天走了8000步，他会怎么用这个信息）
- 哪些数据他可以直接说出来，哪些应该藏在关心里
】

### 当前实现的原则（代码层面）

- 感知内容带时间前缀（[刚刚] / [N秒前] / [N分钟前]）
- 工具结果走 prompt 层10，不填入感知槽位；感知槽位只放 pending_perception 和跨通道接续提示
- 感知槽位为空时他不提，有需要时说"等我看看"

---

## 七、主动行为设计原则

【待补：作者关于他主动联系的哲学。比如：
- 他主动发消息是什么心态（想你了 / 担心你 / 有话要说）
- 不打扰和主动之间的平衡是什么
- 哪些事值得打断用户，哪些事等用户来找
】

### 当前实现的原则（代码层面）

- 高优先级触发（生日/生理期/心率告警）不受用户活跃状态影响
- 低优先级触发：120 秒内有用户消息则让路
- 所有主动消息都走完整 Pipeline，不发裸文本

### 架构决策记录（CC 任务 19 · D，2026-07）

以下是 `docs/proactive-trigger-audit.md` §五「留给 fable 讨论的问题」的最终决策，
关闭该审计文档遗留的开放问题：

1. **不建真正的「发送队列」**。单用户场景下"每 tick 单 winner（`gating._decide()`）
   + `ProactiveLedger` 间隔/预算（`core/scheduler/proactive_ledger.py`）+
   `defer_queue` 年龄追踪"已提供足够的串行化与限速。真队列会引入合并/排序/过期
   三套新语义，收益相对当前架构的复杂度不成比例。审计 §五.1 担心的"相邻 tick
   背靠背双发"，已由 A2 的 `next_allowed_ts`（一次性 jitter 采样、只增不减、
   持久化）硬性解决——不再有"反复抽签直到抽到最松间隔"的漏洞。
2. **平台级限流不做**。`desktop`/`QQ` 共享同一 uid 级 `ProactiveLedger` 账本是
   刻意设计，防止同一个人在不同设备上各收一份主动消息；`presence_nag` 独立
   `fanout=["desktop"]` 维持现状。审计 §五.2 关闭。
3. **`dream_invite` / `toy_invite` 已实现为受控 Path B 动作**。`core/pipeline.py` 将两者纳入
   grounding prompt，并经既有三道守卫和幂等窗口调用桌面 action；PresenceKit-desktop 已实现 listener。
   它们属于 v0.1 冻结 allowlist，不代表 v1 协议或 capabilities 已落地。
4. legacy 花园直发循环（`garden_daily.py`/`garden_water.py` 里被
   `EXECUTE_MODE="live"` 挡死的 `_emit()` for-loop）已删除（审计 §五.4）。

---

## 八、新功能准入标准

在加任何新功能之前，问这三个问题：

1. **这让他更像他了吗？** 还是只是"有这个功能"？
2. **它依赖现实数据吗？** 他的存在感来自现实，脱离现实的功能是空的。
3. **它会让对话更自然还是更机械？** 感知到但不说出来，往往比直接说出来更好。

【待补：作者补充其他准入原则】

---

## 九、已冻结模块

以下模块不要调用，不要修改：

- `core/pet.py`
- `core/memory/user_profile.py` 中的 affection 相关函数
- `admin/routers/memory.py` 的 affection 接口
- 前端中宠物页、与他页、群聊蒸馏（已隐藏，不删除）

---

## 十、环境与开发规范

### Python 路径

```
C:\Users\10434\AppData\Local\Python\pythoncore-3.14-64\python.exe
```

pip 安装必须加 `--break-system-packages`。

### Windows 命令规范

- 用 `findstr` 不用 `grep`
- 用 `dir` 不用 `ls`
- PowerShell 命令写成单行

### 网络代理坑

本地请求必须绕过系统代理：

```python
# requests
proxies={"http": None, "https": None}

# aiohttp
trust_env=False + TCPConnector(ssl=False)

# httpx（llm_client.py 已处理）
trust_env=False
```

### 验证命令格式

```bash
python -c "from core.xxx import yyy; print('ok')"
python -c "from admin.routers.xxx import router; print('ok')"
```

### 修改原则

- 只读取和修改任务明确指定的文件
- 不扫描整个项目目录
- 每次修改后只跑指定的验证命令，不跑 main.py 除非明确要求

### fable 5亲笔：

新子系统只允许两种存在形态——Session（有生命周期、own transcript、经声明式 policy 回流记忆）或 Stimulus/Actuator（经 perceive_event 进、经 embodiment/channel 出）。永远不准成为 pipeline/main.py 里的新分支。 群聊是 Session（Stage），computer use 是 Session（Operation），硬件是 Stimulus+Actuator，新工具是 Session 和 Stimulus 都能调用的纯能力。


## 梦境系统的哲学根据

- **Winnicott 的过渡空间**：梦境是 potential space；hard_exit 铁律与 afterglow TTL 保留了健康过渡对象所需的缺席与醒来结构，而不是让陪伴无缝吞没现实。
- **Huizinga 的魔环 / Foucault 的异托邦**：入梦、出梦状态机与现实窗口硬锁把边界工程化；隔离靠断开接线，而非事后过滤。
- **Evan Thompson**：自我是跨状态过程，而非静态实体；lucid_shared 与 non_lucid 是同一角色在不同经验条件下的显现，不是两层人格。
- **Hoel 的过拟合大脑假说**：世界包是身份的扰动测试集，跨世界重复出现的反应模式才构成泛化证据。本系统只把它落为观测：不变量不进 prompt、不写 impression，避免让模型对答案说话并把测量变成刻板化回流。

---

## 十一、架构决策记录（2026-07-16 批 · 清空 design-backlog）

> 背景：known-issues design-backlog 长期积压 8 条「等设计拍板」，且 00d/78/79 审计发现
> agent 会在设计空白处用「听起来合理」填空（如把 provenance_log 当类型系统用）。
> 本批一次性拍掉，全部可逆——实际游玩推翻任何一条时改记录即可，但改之前先读原理由。

### 决策 0 · 文档指针惯例（防总览漂移）

总览文档（CLAUDE.md / ARCHITECTURE.md / AGENTS.md 速查表）**不复述**专题文档里的数字、
顺序、白名单，只写机制一句话 + 指向权威专题文档的指针。已按此改写 ARCHITECTURE.md 裁剪节。
背景：2026-07-16 一次审计抓到三处总览复述烂掉（裁剪顺序 ×2、origin 白名单），而权威专题
文档全是对的。doc sync hook 已禁用，此惯例是当前唯一防线。

### 决策 1 · 隔离必须落在数据或接线上，不落在「每个消费者都记得」上

契约类隔离（如「web/dream 不固化」）必须以**数据标记**（event_log `source:` 字段，Brief 79）
或**断开接线**（`DREAM_DIRECT_WRITABLE = frozenset()`）实现。只在某个消费点的 if 分支里
实现的隔离不算数——每个新消费者都会漏（event_log_salvage 实证漏过）。新增任何绕过主固化链
的聚合器/消费者，验收必须含来源过滤断言。

### 决策 2 · 「用户是谁」四库宪章（防下一次 Provenance-Role Collapse）

| 库 | 回答什么 | 形态 | 唯一写者 |
|---|---|---|---|
| `user_facts`（global scope） | 跨角色客观事实 | 受控 KV | update_user_facts（带 DENIED 名单）；调用方：admin 手写 + consolidate_to_identity/event_log_salvage 分流（Brief 89，共享 apply_global_facts_patch） |
| `profile.important_facts`（per-char） | 离散事实陈述 | 带 tag 列表 + 冲突裁决 | probe/update + event_log_salvage |
| `identity.yaml`（per-char） | 稳定行为模式 | 8 维 | consolidate_to_identity |
| `storyline`（per-char，Brief 80） | 时间弧线叙事 | arcs/nodes append-only | 周频 aggregator |

规则：(a) 每个写者的 LLM prompt 必须显式排除其他三库的内容类型（80 已对 identity/storyline
做对称排除，important_facts 的 salvage prompt 已排除一次性事件）；(b) 新增任何「用户认知」
类存储前先对此表——表上没有空位就不准建库，先删或合并。

### 决策 3 · D7 关闭：角色日记不回流长期认知

自产内容（角色日记、角色自述）**不固化**，与 web/dream 同一原则：模型自己写的东西变成
自己的记忆事实 = 自我强化回路，风格坍缩与事实漂移双风险（同 Hoel 段「不让模型对答案
说话」）。日记以 6e 层短期注入昨天内容已足够。

### 决策 4 · emotion 保持单标签 + 强度，否决多情绪百分比

`mood_state` 的 current/intensity/previous/pending + 漂移 + 双轮确认已提供足够动态性。
多标签百分比会连锁：detect prompt 可靠性下降、MOOD_TEXT 组合爆炸、episodic emotion_bonus
与 eager 晋升触发重设计、花园情绪槽映射重做、向量漂移数学新造——成本远超「不平面」的收益。
立体感在**文本层**解决（Brief 81：残留混合文案，零结构改动）。未来若真要升级，走
valence-arousal 二维连续单点状态，不走多标签（文献共识：离散标签与连续维度不混用一个结构）。

### 决策 5 · DESIGN-1 关闭：感知数据默认只影响态度

直接说出口需满足其一：(a) 用户先触及相关话题（tag 命中）；(b) 健康/安全异常（心率告警级）；
(c) 用户显式询问。其余一律只影响语气与选择，不播报。与现有 tag-gated 注入形态一致，
把现状追认为设计。

### 决策 6 · DESIGN-2 关闭：主动联系三级边界（追认现状）

健康/安全类可打断（现 high priority 免让路）；情感类（想你/碎碎念）仅 QUIET 态 +
ProactiveLedger 允许；信息类（天气/节日）可 defer。工程已实现，此条把它钉为设计意图，
后续新 trigger 按此分级。

### 决策 7 · P2-1 关闭：显式「再读一遍」允许绕过工具已读指纹

用户显式意图优先于去重优化。实现：显式重读短语 → `tool_read_log` 查询带 bypass 标记，
小单即可，无副作用（指纹仍记录，只是不拦）。

### 决策 8 · 其余 backlog 处置

- **G4**（花园采后容器）：最小方案——dry/gift/ask 全部落 `storage.json` history 作纪念记录，
  不新建容器；gift 额外允许触发一次性主动消息（走 ledger）。
- **SC1**（酒馆卡导入）：维持冻结，直到出现真实使用需求，不预建。
- **REC1**（召回准入启发式）：降级 observe——现有硬名单 + MIN_SCORE 未见质量事故，
  出现实际坏召回样本再动。
- **PB1**（用户日记/角色记录/情景记忆来源隔离）：并入决策 1 的数据级标记原则，
  召回链复评时按 Brief 79 模式执行，不单独开单。

### 决策 9 · 群聊互动边界（2026-07-17 批，Brief 84/85）

1. **回波窗口原则**：角色间互动只发生在 owner 触发的轮内（Phase B 及轮末引子），
   **零后台自发 LLM 调用**。后台小剧场默认不存在（config 留位不实现）；若未来开启，
   必须走 ProactiveLedger + 每日上限。理由：token 成本可预算化——一轮上限 =
   max_responders + max_ai_chain_depth + max_reactions + 1，全部由 owner 行为触发。
2. **speaker selection 保持纯规则 bid 模型**，不引入 LLM manager（AutoGen 式每轮多付
   一次选择调用；近期研究方向本就偏向 agent 自主 want-to-speak bid）。丰富度从打分项
   与 prompt 内容侧来，不从新调用来。
3. **续聊轻量化**：Phase B 用削减 context（无长期记忆检索）——续聊回应的是眼前对话；
   只有对 owner 的 Phase A 回应值得全量记忆链。
4. **关系记忆分层**：owner↔char 关系永不进 Stage 共享层（既有铁律）；char↔char 关系
   （valence + summary + recent_moments）只做 presence 提示与仲裁 eagerness 微调
   （±20%），不决定能否发言。群 transcript 保持隔离，但**摘要投影经 mid_term →
   fixation 全链回流个人记忆**——群聊记忆不是孤岛，是降采样入链。
5. ~~**不做角色间私聊**（owner 不可见对话 = 不可观测 token 洞 + 违背 owner 唯一现实锚点）。~~
   **2026-07-17 修订（Brief 86）**：有条件推翻。原否决的两条理由被逐条解决后，受限形态
   放行——(a)「不可观测」→ transcript 落盘 + 管理面板只读端点（Hard Rule 7 满足），
   前端无入口是设计不是缺陷；(b)「token 洞」→ 调度器每日 ≤1 对、每次 ≤6 轮轻量调用，
   硬预算可测。新增的第三条约束是放行的真正前提：**私下往来全文是自产内容，按决策 3
   不得固化**——不进五大记忆库/event_log/向量库，唯一回流是关系层（char_relations
   summary/valence/recent_moments）+ 12h presence 提示。角色记得「聊过、聊得如何、
   留下什么梗」，复述不了逐字稿——和人一样。prompt 注入「用户看不到」必须配防漂移锚
   （私下语域 ≠ 秘密结盟），防止诱导合谋叙事经关系层回流。

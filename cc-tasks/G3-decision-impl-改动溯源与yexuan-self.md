# G3 · 改动印象溯源 + yexuan-self（决策已替你拍 + 工单）

> 后端（Emerald-presence）。**决策类，你授权我拍**。结论：**不建两个库，建一条 provenance 改动日志 + 两个视图**。
> **前置**：无硬代码前置（可独立开）；与 G2 显式遗忘同属"记忆治理"，建议同人做。
> **可并行**：与注入/梦境/召回簇无冲突。

## 现状（已核对）

- 已有的是**注入/回复溯源**：`core/observe/prompt_capture.py` 按轮捕获注入层 + LLM 输出（ring buffer，内存态），带 `set_capture_origin`（origin: user/proactive/desktop）；层里也有 `_provenance`。
- **缺的是写入侧溯源**：identity（`user_identity.save:88`）、mid_term、episodic 这些**概括被更新/漂移时，没有记录"是哪轮、哪条原始信号导致的改动"**。即"记忆为什么变成这样"不可追。

## 决策：一条日志 + 两个视图（我替你定）

你原本问"要不要单建 yexuan-self 放叶瑄被改变/漂移的部分"。结论：**yexuan-self 不单独建库**，因为它和"改动溯源"是同一个问题（"某个概括为什么变了"）的两种切面。建一条统一 provenance：

- **改动日志**（per-user，新 artifact `provenance_log`）：每次 identity / mid_term / episodic / trait 的**写入/更新**追加一条 `{ts, turn_id, artifact, field, before_gist, after_gist, trigger_signal, origin}`。`origin`/`turn_id` 直接复用 `capture_origin`。
- **视图 A · 改动溯源**：按 artifact/field 查"这条概括什么时候、因为什么变的"。
- **视图 B · yexuan-self**：同一条日志里**筛 artifact ∈ 叶瑄自身（trait/author_note/语气漂移）**的条目 = "叶瑄被用户改变/漂移"的轨迹。是个**过滤视图**，不是新库。

### 关于你说的"现在做来不及了"

诚实讲：**过去的漂移无法回溯重建**（没记就是没记）。但 provenance 是**前向**的——从接入这天起记，往后所有改动可追。所以不是"来不及"，是"从现在开始攒"。早接入早受益。

## 改动点

1. 新 artifact `provenance_log`（path_resolver 加一支，per-user，append-only JSONL，可控大小/滚动）。
2. 在 identity.save / mid_term 写入 / episodic 固化 / trait 更新的**写入点**，各加一行 `provenance_log.append(...)`：记 before/after 的**摘要**（不存全文，gist 即可）+ 当前 `capture_origin` 的 turn/origin + 触发信号（本轮 query 摘要）。
3. 管理端读端点：`GET /provenance/{uid}?artifact=&field=`（视图 A）与 `?scope=yexuan_self`（视图 B 过滤 trait/author_note 类）。
4. （可选）前端只读面板展示两个视图——非必须，先有数据。

## 验收

1. 改一次 identity（触发 consolidation）→ `provenance_log` 出现一条带 before/after gist + turn/origin。
2. 视图 A 能按 field 查到该改动；视图 B 能筛出叶瑄自身漂移条目。
3. 日志 append-only、有大小上限/滚动，不无限膨胀。
4. 不影响主写入路径性能（append 轻量、失败不阻塞写入）。

## 与其他工单的关系
- 与 **G2 显式遗忘** 同簇：遗忘/覆盖发生时也应记一条 provenance（"被用户要求遗忘"）。建议 G2-IMPL 与本工单协同。
- 与 **D2/X3 隔离墙** 一致精神：provenance 也帮助区分"梦/web 来源" vs "现实信号"导致的改动。

## 文档同步
`docs/memory.md` 新增 provenance_log 段与两视图说明；`AGENTS.md` 记"写入点须打 provenance"。

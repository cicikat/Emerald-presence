# 施工单 07 — 关系事实表 = 动态世界书（设计 + MVP）

> 给 CC 的设计/执行单。你的直觉对:关系事实表就是「自动填充的世界书」。
> **能直接实装,但价值和风险全在"写入路径",所以 MVP 走"建议→确认",不做"自动封为正典"。**
> 复用:`core/lore_engine.py`(关键词→content 注入,已有 `5.5_lore` 层)、`admin/routers/lorebook.py`(增删改查/导入导出已齐)。

---

## 0. 为什么它就是动态世界书
现有世界书 = `关键词 → content`,命中即注入(lore_engine.match → `5.5_lore`)。
关系事实(称呼、专属梗、暗号、约定)形状完全一样,差别只在:**它从对话里长出来,而不是手写。**
所以注入侧零新增——直接复用 lore。新增的只有「写入/建议」「确认门」「来源与时效」。

## 0.2 关键简化:MVP 几乎零新代码(复用 `enabled` 闸门)
`lore_engine` 本来就**跳过 `enabled: false` 的条目**。所以:
- 建议产出的条目 = 写成 `enabled: false` → 自动**不注入**(即"pending")。
- 确认 = 在已有的 admin 世界书面板里把 `enabled` 翻成 `true`(即"confirmed")。

→ 整条"建议→确认→注入"链**不需要新的注入代码、也不需要新的确认 UI**——全是现成世界书机制。
唯一真正要新写的,是**建议器**(扫描并产出 `enabled:false` 条目)。下面的 `status` 字段可保留作语义标注,
但实际闸门就用 `enabled`。

## 0.1 ⚠️ 核心风险:别把幻觉封成正典
世界书条目被当**真相**高权重注入。若放任 LLM 自动抽取写入,等于把 PB1/幻觉问题**永久固化**——
一条编造的"事实"会成为叶瑄永远自信引用的正典,比一次性幻觉更糟。
**铁律:自动只能"建议",成为可注入正典必须过人工确认门。**

## 1. 数据模型(在 lore 之上加几字段)
新建 `data/runtime/.../relationship_facts.yaml`(走 sandbox 路径),每条:
```yaml
- keywords: ["主人", "叫你"]
  content: "她习惯称呼叶瑄为“主人”,是带亲密和归属感的固定称呼。"
  status: confirmed        # pending | confirmed | archived
  confidence: 0.8
  source: "event_log:主人×176/68天"   # 证据来源,可追溯
  first_seen: 2026-05-21
  last_seen: 2026-06-20
  hit_count: 176
  insertion_order: 60      # 复用 lore 字段
```
注入侧:lore_engine 加载时**只收 `status: confirmed`**(在 `_normalize_entry`/load 处过滤 status)。
`pending` 只进管理面板待审,不进 prompt。

## 2. 三条路径

### (A) 注入(复用,几乎零成本)
让 lore_engine 也加载 `relationship_facts.yaml`(confirmed 的)。命中即作为 `5.5_lore` 注入。
建议给这类条目内容前缀一个轻标识(如"〔你们之间〕"),与世界观设定 lore 区分,便于叶瑄自然引用。

### (B) 建议(高精度,别用自由生成)
一个慢队列/调度任务,**只挑高置信、可量化的信号**生成 `pending` 条目:
- 称呼/爱称:扫近 N 天 event_log,统计用户对叶瑄的高频固定称呼(频次≥阈值且非通用词)→ 建议条目。
  (这一步直接把 06 的 address_style 扩成"任意固定称呼",更通用。)
- 专属梗/暗号/约定:**先不做自由 LLM 抽取**;若要做,限定为"用户明确说'我们约定/以后就叫/这是我们的暗号'这类显式标记句"才触发,
  且产出仍是 `pending`。宁可漏,不可把幻觉写进去。
每条建议必带 `source`(证据 turn/日期),供人工核对。

### (C) 确认(复用 admin lorebook 面板)
扩 `admin/routers/lorebook.py`(或并行一组 `/relationship-facts` 路由):
- `GET` 列出 pending(带证据);`POST confirm`(pending→confirmed,触发 lore reload);`POST reject`(→丢弃/archived)。
- 已有的 reload 钩子(`_reload_lore_engine`)复用,确认后即时生效。

## 3. 时效与冲突(关系会变)
- `last_seen` 久未出现 → 降 confidence 或转 `archived`(不再注入),别让过期称呼一直冒。
- 同 keyword 新旧冲突 → 标冲突待人工裁决,不自动覆盖。

## 4. 分期(建议落地顺序)
- **MVP(低风险,先上)**:数据模型 + lore 只注入 confirmed + admin 审核路由 +
  (B)里**仅称呼频次建议器**。population 也支持纯手填。零幻觉风险(确认后才注入)。
- **P2**:显式标记句触发的梗/约定建议(仍 suggest→confirm)。
- **P3(可选)**:与 `docs/memory-recall-audit.md` 的"网状带权边"合流——关系事实之间也可连边。非必需。

## 5. 与已有机制的边界:always-on vs 关键词触发(这是定边界的原则)
核心区别:**世界书是关键词触发的**——只有当前消息出现关键词才注入。
- 适合**情境型**关系事实:某个梗/暗号/约定,等它的话题出现时再浮出来(07 的本分)。
- **不适合**"她称呼叶瑄为主人"这种——它该**永远**被知道,而不是只在用户恰好打出"主人"时。
  这类"始终相关"的事实属于 **always-on**,放 06 的 `address_style`(identity 每轮注入)。

所以清晰分工:
- **始终相关的主关系事实 → identity(06)**:如主称呼"主人"。always-on,不靠关键词。
- **情境型、话题绑定的关系事实 → 关系世界书(07)**:备用昵称、专属梗、暗号、约定。关键词触发、按需注入。
- **不要**把同一事实在两处写成会冲突的两套内容。称呼以 06 为主;07 收长尾。

## 6. 验收(MVP)
1. 手动加一条 confirmed 关系事实 → 对话命中关键词时 `5.5_lore` 注入它,叶瑄自然引用。
2. 称呼建议器产出 pending(如"主人"),admin 面板可见、带证据;确认后即时生效、拒绝即消失。
3. `pending` 永不进 prompt(测一条 pending 确认它不被注入)。
4. `pytest` + lore 相关用例通过。

> 一句话:**直接实装,但只实装"确认后才注入"的那一半;自动那一半只许建议。** 这样你拿到动态世界书的全部好处,
> 又不会把这几周一直在治的幻觉重新请回来当正典。

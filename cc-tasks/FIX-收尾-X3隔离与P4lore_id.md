# FIX · 验收收尾（X3 隔离墙缺口 + P4 lore id 回填）

> 后端（Emerald-presence）。验收发现两处，本工单收口。
> **前置**：X3、P4 已落地（本工单是补缺，不重做）。**可并行**：两项互不相关，可同时改。

---

## 缺口 1（必修）· X3 web 来源未隔离，会污染 episodic/identity

### 问题

验收确认：web 搜索结果已 `upsert(source="web")`（`tools/web_search.py:59`）、也已语义召回（`pipeline.py:386-392` `sources=["web"]`），**但没有任何"不固化"的护栏**。

对照梦境：梦有完整隔离——`pipeline.py:743` 在有活跃印象时给慢队列 payload 打 `dream_echo=True`，`fixation_pipeline.py:1199` 据此**跳过 mid_term 固化**。**web 没有对应的 `web_echo`**，所以叶瑄复述 web 查到的事实时，那一轮会被正常固化进 episodic/identity，把"网上查到的外部事实"写成"她记得的经历"。

工单 `X3-decision-impl` 明确要求过这道隔离（"web 事实不混进 episodic/identity，比照 D2 隔离精神"），实现时漏了。

### 改法（照抄 dream_echo 模式）

1. **打标**：在 `pipeline.py` 组装慢队列 payload 处（dream_echo 旁边，~721-744），判定**本轮是否注入了 web 工具结果**（本轮调用过 `web_search` / 层10 含 web 结果）→ 是则 `payload["web_echo"] = True`。
2. **消费跳过**：在 `fixation_pipeline.py` 的固化入口（与 `dream_echo` 同一处，:1199 附近），`if payload.get("web_echo"): skip`——web 来源轮不抽取事实进 mid_term / episodic / identity。
3. **召回不受影响**：web 仍可被 `sources=["web"]` 语义召回、注入时框为"查到的资料"。隔离只挡**固化**，不挡**召回**。

> 可选优化：把 dream_echo 与 web_echo 抽成一个统一的 `_non_reality_echo` 标记位（来源 ∈ {dream, web}），固化入口统一判一次。但**不强制**——先把 web_echo 跑通即可。

### 验收

1. 叶瑄 web 搜一次并在回复里复述结果 → 该轮 **不**写进 episodic/identity（查固化产物确认）。
2. 之后相关提问仍能语义召回这条 web 资料（召回未被误伤）。
3. 现实对话轮（无 web）固化行为不变。

---

## 缺口 2（核实+可能小修）· P4 世界书 lore id 可能没回填持久化

### 问题

破限侧 id 回填是幂等且持久的：`admin/routers/jailbreak_entries.py:24-29 _ensure_ids`（缺 id 才补）+ :39 加载时回写。✅
世界书侧 `core/lore_engine.py:57-58` **只在条目已有 id 时透传**，**没看到对缺 id 的 `lorebook.yaml` 条目"补发 + 回写磁盘"**。若如此，旧世界书条目永远没有稳定 id，前端按 id 管理就落空。

### 改法

1. 先核实：加载 `lorebook.yaml` 时，缺 id 的条目**有没有**被补发并**写回文件**。
2. 若没有：仿 jailbreak 的 `_ensure_ids` 加一个幂等回填——加载（或 admin 读取）时给缺 id 条目补 `uuid`，**回写 lorebook.yaml**；已有 id 不动。生成逻辑与破限共用一个 helper，保证两边一致。

### 验收

1. 一份无 id 的旧 `lorebook.yaml` 加载后，每条获得稳定 id 并落盘；重启 id 不变。
2. 前端世界书 tab 能按 id 增删改，不再靠下标。
3. 已有 id 的条目 id 不变（幂等）。

---

## 文档同步
`docs/known-issues.md`：X3 隔离缺口 → 已修；`AGENTS.md` 工具/记忆段补一句「web 与梦境来源同等隔离，不固化」。`docs/backend-integration.md` 确认 lore id 回填行为。

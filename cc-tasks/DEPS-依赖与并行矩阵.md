# DEPS · 全工单依赖 / 并行 / 前置矩阵

> 本文是调度参考。回答三件事：每张单**能不能现在开**、**卡在谁后面**、**哪些能真并行不打架**。
> 关键认知：**X1 和 P1 已落地验收**，所以"逻辑前置"几乎都已满足——现在主要约束不是"等依赖"，而是**多张单改同一个文件**（文件竞争）和**少数接口先后**。

---

## 1. 状态总表

| 单 | 状态 | 逻辑前置 | 主要落点文件 | 类型 |
|---|---|---|---|---|
| X1 向量库 | ✅ 已落地验收 | — | `core/memory/vector_store.py`, `embedding.py` | 根 |
| P1 注入骨架 | ✅ 已落地验收 | — | `core/prompt_builder.py` | 根 |
| F1 词级强调 | 🟢 可开 | 无 | `prompt_builder.py`(author_note) + 角色卡 mes_example | 小修 |
| F2 标题+自主看内容 | 🟢 可开 | 无 | `prompt_builder.py`(realtime) + 新 `screen_peek.py` + admin + **前端** | 跨仓 |
| TOY 自主写入 | 🟢 可开(p1) | p2 依赖 X1✅ | `core/post_process/` + `toybox.py` | 中 |
| P2 工具回写 | 🟢 可开 | G1✅(已结) | `prompt_builder.py`(层10) + `short_term.py` | 中 |
| P3 画像单条化 | 🟢 可开 | P1✅; 语义增强用 X1✅ | `prompt_builder.py`(层5) + `user_profile.py` | 中 |
| P5 称呼清洗 | 🟢 可开 | P1✅(seam 已就位) | `prompt_builder.py`(`_normalize_injection`) | 小修 |
| P4 加id+前端统一 | 🟢 可开 | 无 | `lore_engine.py` + `jailbreak_entries.py` + **前端** | 跨仓 |
| D1 mesexample 修 | 🟢 可开 | 无 | `dream/world_loader.py` 或世界包文件 | 小修 |
| D2 impression 细粒度 | 🟢 可开 | D1✅(已诊断) | `dream/distill_impression.py` + 固化隔离 | 大改 |
| D3 梦境现实衰减 | 🟢 可开 | 无 | `dream/dream_context.py` + `dream_prompt.py` | 小改 |
| X2 召回评分 | 🟢 可开 | X1✅(强依赖) | `vector_store.score_recall` + `event_log.py` | 中 |
| X3 自己上网 | 🟢 可开 | X1✅ | `tools/web_search.py` + `vector_store` | 中(决策已拍) |
| G2 显式遗忘 | 🟢 可开 | X1✅(删向量) | `memory/*` 删除入口 + admin + 前端 | 中 |
| G3 溯源/yexuan-self | 🟢 可开 | 无 | 新 `provenance_log` + 各写入点 | 中(决策已拍) |

> 没有任何单还卡在"未完成的逻辑前置"上——根已落地。下面是**真正的约束**。

---

## 2. 文件竞争（同一文件多单同改 → 别同时改，会冲突）

### ⚠️ A. `prompt_builder.py` 竞争组（**6 张单都改它**）

P5(normalize 钩子) · P3(层5) · P2(层10) · D2(层6g 标签) · F1(author_note) · F2(realtime)。

各自改**不同层**，逻辑不冲突，但同文件并发会产生 git 冲突。**建议：这 6 张串成一条线、同一执行者按序做**，推荐顺序（结构性的先）：

```
P5(清洗钩子) → P3(层5重构) → P2(层10回写) → D2(6g标签) → F1(author_note) → F2(realtime片段)
```

### ⚠️ B. `vector_store` / 召回 竞争组（接口先后）

**X2 必须先做**——它修 X1 遗留的 距离→相似度 符号问题、并定下 `score_recall` 融合公式。之后这些才接它：
- P3 的"语义召回偏好"
- X3 的 web 来源召回
- TOY phase2 的 toy 来源召回
- G2 的删向量

```
X2(定标 score_recall + 符号) → { P3语义增强, X3, TOY-p2, G2删向量 } 并行
```

### ⚠️ C. 前端竞争组

F2(设置页开关) 与 P4(破限/世界书统一面板) 都动 client。不同组件，冲突小，但同一前端执行者协调更顺。

---

## 3. 三条可并行主线（互不碰文件）

> 把 16 张单按"碰不碰同一文件"分成三条线，**线与线之间真并行**，线内按序。

| 主线 | 单（按序） | 碰的文件域 |
|---|---|---|
| **线 1 · 注入** | P5 → P3 → P2 → D2 → F1 → F2(后端片段) | `prompt_builder.py` |
| **线 2 · 召回/自主** | X2 → (X3 ∥ TOY-p2 ∥ G2删向量) | `vector_store`/`event_log`/`tools` |
| **线 3 · 独立** | P4 ∥ D1 ∥ D3 ∥ G3 ∥ TOY-p1 | 各自独立文件 |

跨线协调点：
- **F2 / P4 的前端部分** 汇到同一个前端执行者（线1后端 + 线3 各出一段前端，前端侧串一下）。
- **G2 与 G3** 同属记忆治理，建议同人（遗忘要写 provenance）。
- **D2 的"固化隔离"** 与 **X3 的"web 不固化"** 是同一道隔离墙精神，做 D2 时把这道墙做成可复用的，X3 直接用。

---

## 4. 建议执行波次（综合依赖 + 文件竞争）

| 波 | 并行内容 | 说明 |
|---|---|---|
| **波 1** | 线3 全部（P4 / D1 / D3 / G3 / TOY-p1）+ 线1 起步（P5→P3）+ 线2 起步（X2） | 全是独立或已解锁，最大并行 |
| **波 2** | 线1 续（P2→D2→F1→F2）+ 线2 续（X3 / TOY-p2 / G2） | 依赖波1的接口（X2 定标、D2 隔离墙） |
| **波 3** | 前端收口（F2 设置页 + P4 面板）+ 各 `docs/` 同步 + 回归测试 | 跨仓收尾 |

---

## 5. 全局硬约束（所有单通用）

1. 改 `prompt_builder.py` 任何层后跑 `python tests/run_eval.py` + `test_r4_*`。
2. 改 short_term 写入必经 `_sanitize_assistant_message`（CLAUDE.md 规则5）。
3. 所有 `data/` 路径走 `core/sandbox.get_paths()`（规则1）；新 artifact 进 `path_resolver`。
4. 向量/embedding/web 一切外部调用 **fail-open**，绝不阻塞主回复。
5. 梦境 / web / 外部来源内容**不固化进 episodic/identity**（D2 立的隔离墙，X3 复用）。
6. 跨仓改前端读 client `AGENTS.md`；HTTP 走 Tauri command，集中 `src/shared/api/`。

> 一句话调度：**波1 三线齐开**（线3 随便排、P5→P3 起手、X2 定标），波2 各线接着跑，波3 前端+文档+测试收口。

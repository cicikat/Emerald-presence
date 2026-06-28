# G2-IMPL · 显式遗忘 / 覆盖（管理端粒度删除 + 向量连带删 + provenance）

> 后端（Emerald-presence）+ 可选前端。诊断见 `W0-诊断结论.md` §G2。
> **前置**：X1 向量库（✅ 已落地）——删记忆要连带删向量。与 **G3**（✅ 已落地）协同：遗忘要记一条 provenance。
> **可并行**：与其余工单无冲突。
> **方向（已定）**：先做**管理端显式操作**（手动删/盖某条），自然语言"忘了它"留二期。

## 现状（已核对）

- **遗忘是空白**：无 forget 工具；各记忆层只增不显式删。
- **现有删除端点过粗**：`admin/routers/memory.py:63 DELETE /{uid}/short-term`（清空短期）、`users.py:144 DELETE /{uid}/memory`（清空**全部**记忆）——要么不删要么全清，没有"删某一条"。
- **唯一的粒度先例**：`relationship_facts.py:182 DELETE /relationship-facts/{uid}/{index}`（按 index 删一条）——**照这个粒度做**。
- **向量库无 delete**：`vector_store.py` 只在 upsert 内部 `DELETE FROM vec_items`（重插用），**没有对外 delete API**。

## 改动点

### 1. vector_store 加对外 delete（X1 收尾）

`core/memory/vector_store.py` 加：
```python
def delete(uid, char_id, source, source_id) -> bool:
    """按 (source, source_id) 删 vec_meta + vec_items 对应行。fail-open。"""
```
靠现有 `vec_meta(source, source_id)` 定位 rowid，删两表。删记忆条目时同步调用。

### 2. 各记忆层加"删一条 / 覆盖一条"入口

给这些层补粒度删除（覆盖 = 删旧 + 写新），统一走各自的 `safe_write_*`：

| 层 | 文件 | 删除键 |
|---|---|---|
| episodic | `episodic_memory.py` | 条目 `id` → 删条目 + `vector_store.delete(source="episodic", source_id=id)` |
| profile.important_facts | `user_profile.py` | index / text → 删条目（+ 若已向量化则连带删） |
| profile.pinned_facts | `user_profile.py` | index / text |
| user_identity 维度 | `user_identity.py` | 维度 key → 清空/覆盖某维度 |
| mid_term | `mid_term.py` | 时间桶 / 条目 id |
| user_facts | `user_facts.py` | index / key |
| event_log | `event_log.py` | （粒度较难，先支持按天文件删/标记，最低限度） |

### 3. 管理端端点（仿 relationship_facts 粒度）

每层补 `DELETE /memory/{uid}/{layer}/{key}`（或各层对应路由），返回删除结果。覆盖用 `PUT`/`POST`。

### 4. 每次遗忘记一条 provenance（与 G3 协同）

删除/覆盖发生时调 `provenance_log.append(...)`，`trigger_signal="explicit_forget"`、`origin="admin"`，记 before gist。这样"被用户要求遗忘"也进了改动溯源。

### 5. （可选）前端面板

记忆查看面板里每条加"删除/编辑"，按 key 调上面端点。集中在 `src/shared/api/`，HTTP 走 Tauri command。**非必须，后端端点先到位**。

## 验收

1. 删 episodic 一条 → 该条从 `episodic.json` 消失，且 `vector_store` 里对应向量同步消失（语义召回不再命中它）。
2. 覆盖 profile 一条 → 旧值消失新值生效。
3. 每次删除/覆盖 → `provenance_log` 多一条 `explicit_forget`。
4. 粗端点（清空全部）行为不变，不受影响。
5. 删不存在的 key → 优雅返回，不崩。

## 二期（留记，不做）
自然语言"忘了它/别记这个"的**意图识别** → 自动触发遗忘。需探针加一个 forget intent，风险是误删，故先只做管理端显式操作。

## 文档同步
`docs/memory.md` 记各层粒度删除 + `vector_store.delete`；`docs/backend-integration.md` 记新端点；`known-issues.md` G2 标已修。

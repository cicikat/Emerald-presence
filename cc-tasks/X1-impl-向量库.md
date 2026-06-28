# X1-IMPL · 向量库施工 brief

> 后端（Emerald-presence）。动手前读 `AGENTS.md` 与本仓 `core/memory/` 现状。
> 设计判定见同目录 `X1-decision-向量库.md`，**本文不再重述取舍，只给施工要点**。
> 用户已授权下列判定，CC 直接施工，无需再问设计意图：
> **存储=sqlite-vec；embedding 阶段 A=OpenAI 兼容 API（A1，已拍）；向量库=可重建索引，JSON/MD 仍是真相源。**
> **改造档位：纯新增 + 两个细缝挂接**（不改任何现有记忆文件格式，不动现有关键词召回路径，只在其旁并联一条语义召回）。

---

## 背景与目标

现状（已核对）：

- 全部记忆是散文件，**无任何数据库**：`episodic.json` / `memory_index.json` / `event_log/*.md`，`data/` 共 47MB。
- **全后端无 embedding 能力**（`requirements.txt` 无 torch / sentence-transformers / 任何 embedding 依赖）。
- 召回相关性靠**字符 n-gram 关键词重叠** `relevance = hit / len(keywords)`（`event_log.py:382/409`），粒度粗。
- `memory_index.json` 已经是「**派生数据、坏了从记忆重建**」的模式（`episodic_memory.py:108-114`）——向量库**沿用同一哲学**。

目标：并联一条**语义召回**通道，喂给 P3（画像召回）和 X2（query relevance 评分）。**不替换** tag/关键词路径，tag 降为粗筛、向量做细排。

---

## 关键事实（已核对，施工依赖）

| 事实 | 出处 | 对施工的意义 |
|---|---|---|
| 每用户记忆根 `user_memory_root(uid, char_id)` | `path_resolver.py:107-153` | 向量库 db 放这里，**per-user**，天然按 char_id/uid 隔离，省掉 chroma 式分区 |
| 新存储要走 artifact 表 | `path_resolver.py:20-35,82-153` | **新增 artifact key `vector_store`**，进 `REALITY_USER_ARTIFACTS`，resolver 加一支 |
| `data/` 全量 gitignore | `.gitignore:2` | **`.db` 自动不进 git**，满足「聊天数据不上 github」。无需额外配置 |
| 配置走 `config.yaml` 的 `model_presets` 风格块，且 `config.yaml` 已 gitignore | `config.yaml`、`.gitignore` | embedding 配置新增一个 `embedding:` 块，**api_key 只写 config.yaml，绝不写进本 brief / 代码 / 提交** |
| 召回在 pipeline 调 | `pipeline.py:224` `event_log.search(...)` | 语义召回在此并联；query embedding 在此算一次复用 |
| `safe_write_json` / 派生可重建 | `episodic_memory.py:85,108` | 向量库出错一律 **fail-open**：删库重建，绝不阻塞主回复 |

---

## 施工要点

### 1. 依赖

`requirements.txt` 加 `sqlite-vec>=0.1.0`（一个小的 sqlite 可加载扩展，无重依赖）。embedding 复用已装的 `openai` SDK，**不新增**。

### 2. embedding 边界（最重要——决定未来上服务器能否一行切换）

新建 `core/memory/embedding.py`，**唯一对外口子**：

```python
async def embed(texts: list[str]) -> list[list[float]]:
    """文本 → 向量。批量。失败抛 EmbeddingUnavailable（调用方 fail-open）。"""
```

- provider 从 `config.yaml` 的 `embedding:` 块读：`provider_kind` / `base_url` / `api_key` / `model` / `dim` / `batch_size`。
- 阶段 A 实现 `openai_compat` 一种 provider（OpenAI 兼容 `/embeddings`，复用 `openai` SDK）。
- 预留 `self_hosted`（阶段 B 上服务器用，HTTP 调自托管端点）——**只留接口分支，本期不实现**。
- 上层永远只 import `embed`，**禁止**任何模块直接拼 embedding HTTP/SDK 调用。

`config.example.yaml` 加注释样例块（**占位 key，不写真 key**）：

```yaml
embedding:
  provider_kind: openai_compat
  base_url: https://your-embedding-endpoint/v1
  api_key: YOUR_EMBEDDING_KEY          # 真 key 只进 config.yaml（已 gitignore）
  model: bge-m3                          # 或任意中文 embedding 模型
  dim: 1024                              # 必须与 model 输出维度一致
  batch_size: 32
```

### 3. 向量存储 `core/memory/vector_store.py`

- per-user db：新增 artifact `vector_store` → `user_memory_root/vector_store.db`。
- 建表（sqlite-vec `vec0` 虚拟表 + 旁挂元数据表）：

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding float[DIM]);
CREATE TABLE IF NOT EXISTS vec_meta (
  rowid INTEGER PRIMARY KEY,   -- 对齐 vec_items.rowid
  source TEXT,                 -- 'episodic' | 'event_log' | 'profile'
  source_id TEXT,              -- 回指真相源里的条目 id / 文件+块
  ts REAL,                     -- 原始时间戳，供 recency / 衰减
  text_preview TEXT            -- 仅用于调试/溯源，非真相
);
```

- 对外 API（全部同步、内部开关 db；写失败只 log 不抛到主流程）：
  - `upsert(uid, char_id, source, source_id, ts, text)` —— 内部调 `embed([text])` 后写两表。
  - `query(uid, char_id, query_vec, k, *, sources=None, since_ts=None) -> list[(source_id, score, ts)]` —— KNN（sqlite-vec `MATCH` + `k`），可按 source / `since_ts` 过滤。**recency（P3「只召最近」）= 传 `since_ts`；时间衰减由调用方在 score 上乘系数。**
  - `rebuild(uid, char_id)` —— 删表重建：从 episodic.json + event_log 批量 embed 回填。
- **DIM 校验**：写入/查询前断言 `len(vec)==config.dim`，不一致直接 fail-open 并 log（防换模型忘改 dim）。

### 4. 挂接点（两条缝，别改现有逻辑）

1. **写入**：episodic 落盘处（`_save_memories` 之后的 consolidate 链）追加 `vector_store.upsert(...)`；event_log 每日/每轮写块处同理。用 `create_task` 或慢队列，**绝不进主回复关键路径**。
2. **召回**：`pipeline.py:224` 附近，对 `content` 算一次 `embed([content])`，并联 `vector_store.query(...)` 拿语义候选；与现有 `event_log.search` / episodic tag 召回的结果**合并去重**。合并打分先用最简：`final = semantic_score + 现有 strength×decay`（X2 会替换成正式融合公式，这里**留一个 `score_recall()` 单点函数**给 X2 接管）。

### 5. fail-open 契约（硬要求）

embedding API 超时/报错、db 缺失/损坏 → **静默回退到现有关键词召回**，主回复不受影响、不报错给用户。所有向量路径包 try/except + log，参照现有 `_load_index` 重建容错。

---

## 验收

1. `pytest` 全绿；新增 `tests/test_vector_store.py`：建表/upsert/query/dim 不匹配 fail-open/rebuild 幂等。
2. **断网验收**：embedding 端点不可达时，召回自动走老路径，回复正常（证明 fail-open）。
3. **重建验收**：删掉 `vector_store.db` 后调 `rebuild`，query 结果与删除前一致。
4. `git status` 确认 `vector_store.db` 未被追踪。
5. 跑一条真实 query，日志打印语义候选 top-k 的 `(source_id, score)`，人工核对相关性优于关键词路径。

## 解锁

P3（画像召回用 `query(sources=['profile'], since_ts=...)`）、X2（接管 `score_recall()`）、X3（网页结果 `upsert(source='web')` 即得自检索库，复用同一 db 与 `embed()`）。

## 文档同步

新增 `docs/vector-store.md`（schema + embed 边界 + fail-open 契约 + 阶段 A/B 切换）；`docs/memory.md` 末尾加一段指向它。

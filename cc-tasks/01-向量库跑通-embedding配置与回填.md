# CC 任务：向量库跑通 — embedding 配置缺失 + 回填 + 验证

> 给 Claude Code 执行。开工前按 `AGENTS.md` 读 `docs/vector-store.md`。
> 改动集中在 `config.yaml`（补配置）、环境（装 sqlite-vec）、一个一次性回填脚本，
> 以及可选的 admin「重建」按钮。**不改召回算法本身**——库一旦有数据，现有路径就生效。

---

## 背景（现状已确认，2026-06-29 实读）

管理面板显示「向量库 总条数 0 · 维度 1024」，但 bot 已跑了好几天。根因是**两个**，第一个是致命的：

### 根因 1（致命）：`config.yaml` 根本没有 `embedding:` 块

- `grep -c "^embedding:" config.yaml` → **0**。真实 `config.yaml` 里没有这一块（`config.example.yaml` 第 213 行才有）。
- `core/memory/embedding.py::_load_config()` 在 `embedding` 块缺失时直接 `raise EmbeddingUnavailable("embedding block missing in config.yaml")`。
- `core/memory/vector_store.py::upsert()`（第 88–100 行）捕获 `EmbeddingUnavailable` 后 **静默 skip**（fail-open 设计）：
  ```python
  try:
      vecs = await embed([text])
  except EmbeddingUnavailable as e:
      logger.info("[vector_store] embedding unavailable, skip upsert ...")
      return   # ← 每一条 upsert 都走这里，永远写不进
  ```
- 唯一的写入点 `core/memory/fixation_pipeline.py:906`（episodic 晋升时 `asyncio.ensure_future(_vs.upsert(...))`）因此每次都被吞掉。
- 而面板那个「维度 1024」是假象：`vector_store.py::stats()` 在库为空/打不开时返回 `{"total": 0, "dim": _configured_dim()}`，`_configured_dim()`（第 22–27 行）读不到配置就 `return 1024` 默认值。**所以「0 条 · 1024 维」恰恰是「从未配置过 embedding」的标准症状，不是维度对上了。**

### 根因 2（可能）：`sqlite-vec` 未安装

- `requirements.txt` 里有 `sqlite-vec>=0.1.0`，但需确认运行环境真的装了。
- `vector_store.py::_open_db()`（第 39–45 行）`import sqlite_vec` 失败时 `logger.debug("sqlite_vec not installed; semantic recall disabled")` 后返回 `None`，同样 fail-open 到 0 条。
- 即使根因 1 修好，若 sqlite-vec 没装，库依然是 0。

---

## 目标

1. 在 `config.yaml` 补 `embedding:` 块，指向一个可用的 OpenAI 兼容 `/embeddings` 端点。
2. 确认 `sqlite-vec` 已安装。
3. 跑一次性 `rebuild()` 把已有 `episodic.json` + `event_log` 回填进向量库。
4. 在面板 / 日志确认「总条数 > 0」，且语义召回真的命中。

---

## Part 1 — 补 `config.yaml` 的 embedding 块

把下面这段加进 `config.yaml`（紧挨现有 `recall:` 之前；若没有 `recall:` 块也一并补上，召回融合权重要用）。**真 key 只进 `config.yaml`（已 gitignore），不要进 `config.example.yaml`。**

```yaml
# ── 语义 Embedding（向量召回，见 docs/vector-store.md）──
embedding:
  provider_kind: openai_compat
  base_url: https://<你的-embedding-端点>/v1   # 例：硅基流动 / 本地 bge / 任意 OpenAI 兼容
  api_key: <真实 key>
  model: bge-m3                                # 中文 embedding 模型
  dim: 1024                                    # ★ 必须与 model 实际输出维度严格一致

recall:
  weights:
    sem: 0.4
    kw: 0.3
    strength: 0.3
  batch_size: 32
```

> ⚠️ **`dim` 必须等于 model 真实输出维度**。`vector_store.py::upsert()` 第 105 行有维度校验：
> `got != expected` 时打 `dim mismatch ... skip upsert` 然后 skip。bge-m3 是 1024；若换模型（如 `text-embedding-3-small`=1536）要同步改 `dim`，否则又是 0 条。
>
> ⚠️ 表一旦用某个 `dim` 建好（`CREATE VIRTUAL TABLE vec_items USING vec0(embedding float[N])`），改 `dim` 必须删库重建（见 Part 3），不能就地改。

**需要茶茶确认/提供**：embedding 端点 + key + 模型 + 维度。这是唯一的人工输入项，CC 拿不到就先留占位并在 PR 里标 TODO。

---

## Part 2 — 确认 sqlite-vec 安装

```bash
python -c "import sqlite_vec; print('sqlite_vec', sqlite_vec.__version__)"
```

报 `ModuleNotFoundError` 就装：

```bash
pip install sqlite-vec>=0.1.0
```

注意 `_open_db()` 走的是 `sqlite3` + `db.enable_load_extension(True)` + `sqlite_vec.load(db)`。某些 Windows 自带的 python `sqlite3` **未开启 `enable_load_extension`**，会在加载扩展时抛异常→fail-open 到 0 条。若装了包但库仍空，按这个顺序排查：先看日志有没有 `cannot open db`，再确认 python 的 sqlite3 支持 load_extension（`python -c "import sqlite3;sqlite3.connect(':memory:').enable_load_extension(True)"` 不报错才算 OK）。

---

## Part 3 — 一次性回填（rebuild）

`vector_store.py::rebuild(uid, char_id)`（第 216 行起）已实现：删表重建，从 `episodic.json` 批量 upsert + 把近 30 天 `event_log` 拼成一条 recent_text 写进去，返回写入条数。但**目前没有任何调用点**（grep 确认：admin 无按钮、无 CLI）。新增一个一次性脚本：

新建 `scripts/rebuild_vector_store.py`：

```python
"""一次性回填向量库。用法：python scripts/rebuild_vector_store.py [uid] [char_id]
不带参数时遍历 data/runtime/memory/{char_id}/{uid}/ 下所有 (char_id, uid)。"""
import asyncio, sys
from pathlib import Path
from core.memory import vector_store as vs
from core.sandbox import get_paths

async def _one(uid: str, char_id: str):
    n = await vs.rebuild(uid, char_id)
    print(f"[rebuild] char={char_id} uid={uid} -> {n} 条")

async def main():
    if len(sys.argv) >= 3:
        await _one(sys.argv[1], sys.argv[2]); return
    # 没有 memory_root() helper；user_memory_root 返回 .../memory/{char}/{uid}，
    # 取 .parent.parent 拿到 data/runtime/memory 根
    root = get_paths().user_memory_root("x", char_id="y").parent.parent  # data/runtime/memory
    for char_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for uid_dir in sorted(p for p in char_dir.iterdir() if p.is_dir()):
            try:
                await _one(uid_dir.name, char_dir.name)
            except Exception as e:
                print(f"[rebuild][skip] {char_dir.name}/{uid_dir.name}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

> 跑之前**先确认 Part 1 的端点真的通**（否则 rebuild 里每条 embed 又会 EmbeddingUnavailable→skip，白跑还是 0）。可先小验：
> ```bash
> python -c "import asyncio; from core.memory.embedding import embed; print(len(asyncio.run(embed(['测试']))[0]))"
> ```
> 应打印出维度数字（如 1024）。报错就回去修 Part 1。

跑回填：

```bash
python scripts/rebuild_vector_store.py            # 全量
# 或仅当前主用户（实读盘上存在的）：
python scripts/rebuild_vector_store.py 1043484516 yexuan
```

> 盘上已确认存在的真实用户目录：`yexuan/1043484516`、`yexuan/2985713106`、`yexuan/owner8`、`hongcha/1043484516`、`hongcha/2985713106`。

**（可选，体验更好）** 顺手在 admin 加个「重建向量库」按钮：在 `admin/routers/observe.py`（已有 `vs.stats(uid, cid)` 那个 endpoint 同级）加一个 `POST /vector/rebuild/{uid}` 调 `await vs.rebuild(uid, cid)` 并返回新 stats。前端「向量库」观测页（admin-panel cc-task 已建/在建）加个按钮调它。非必须，但便于以后换模型后一键重建。

---

## Part 4 — 验收标准

1. `python -c "import asyncio; from core.memory.embedding import embed; print(len(asyncio.run(embed(['测试']))[0]))"` 打印出与 `dim` 一致的维度数，不抛 `EmbeddingUnavailable`。
2. 跑完 Part 3 后，`vector_store.stats("1043484516","yexuan")["total"] > 0`；管理面板向量库页「总条数」非 0、`by_source` 里有 `episodic`（可能还有 `event_log`）。
3. 新一轮对话触发 episodic 晋升后，日志**不再**出现 `embedding unavailable, skip upsert`；`vec_items` 行数随之增长。
4. 语义召回真的命中：用一句和某条 episodic 语义相近但**关键词不同**的话提问，确认 `episodic_memory` 召回里出现该条（说明 `score_recall` 的 `w_sem` 项生效，而非纯关键词）。
5. fail-open 不回归：故意把 `base_url` 写错跑一轮对话，主回复**正常**、只是日志回到 skip——证明向量库出错不影响主链路。

---

## 备注

- 向量库是**派生数据**，`episodic.json` / `event_log` 才是真相源；库随时可删可重建，不进 git（`vector_store.db` 已 gitignore）。
- 这次只让它「跑起来 + 回填历史」。召回权重调参（`recall.weights`）属后续调优，不在本单。

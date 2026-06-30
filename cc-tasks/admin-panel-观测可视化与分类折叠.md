# CC 任务：管理面板 — 观测可视化（向量库 + 印象溯源）+ 侧边栏分类折叠

> 给 Claude Code 执行。全部改动集中在 `admin/static/index.html`、`admin/routers/observe.py`、
> `core/memory/vector_store.py` 三个文件。后端「向量库 / provenance 溯源」逻辑已建好，本次主要是
> **把它们接到管理面板 + 重排侧边栏**。开工前按 `AGENTS.md` 读 `docs/vector-store.md`。

---

## 背景（现状已确认）

- 侧边栏（`admin/static/index.html` 约 288–311 行）是扁平结构：四个纯文本分类标题 div + 一堆 `<a data-page>` 链接，靠 `goto(page)` 切页。
- `GET /provenance/{uid}` **后端已完整**（`admin/routers/observe.py` 同级的 `admin/routers/provenance.py`，已在 `admin_server.py` 注册），返回每条概括「何时、因何、从哪条聊天记录」改动的日志。**但前端没有任何页面消费它。**
- 向量库 `core/memory/vector_store.py` **已建好**（sqlite-vec，表 `vec_items` + `vec_meta(source, source_id, ts, text_preview)`），但**没有任何只读观测接口**，管理面板也看不到。
- 当前分类：`🎭 叶瑄`(标签) / `🎨 创作` / `🛠 运维` / `🔍 观测/调试`。

## 目标

1. 删掉 `🎭 叶瑄` 标签。
2. 侧边栏改成 4 个**可独立点击折叠**的分组（同一层级），折叠状态记进 `localStorage`：
   - `🎨 创作`：角色卡、现实设定、梦境设定
   - `🛠 运维`：系统状态、调度器、用户管理、错误日志
   - `🔬 内部状态`（原「观测/调试」改名）：情绪·花园、梦境状态、记忆探查、隐性状态、聊天日志、运行时内部态
   - `🔍 观测`：Prompt 层检视、探针观测、梦境 Prompt、触发器目录、**+ 向量库(新)** 、**+ 印象溯源(新)**
3. 新增两个观测页：**印象溯源**（接已有 `/provenance`）、**向量库**（需新增后端接口）。

---

## Part 1 — 后端：向量库只读接口

### 1.1 `core/memory/vector_store.py` 末尾新增两个只读 helper

风格对齐文件里现有的 `query_with_preview`（fail-open、`db.close()` 在 finally）。注意：查询前先
`_ensure_tables(db, _configured_dim())`（`CREATE ... IF NOT EXISTS`，无副作用，防空库报错）。

```python
def stats(uid: str, char_id: str) -> dict:
    """向量库概览：总条数 + 按 source 分组计数。fail-open → 全 0。"""
    db = _open_db(uid, char_id)
    if db is None:
        return {"total": 0, "by_source": {}, "dim": _configured_dim()}
    try:
        _ensure_tables(db, _configured_dim())
        rows = db.execute(
            "SELECT source, COUNT(*) FROM vec_meta GROUP BY source"
        ).fetchall()
        by_source = {(r[0] or "unknown"): r[1] for r in rows}
        return {"total": sum(by_source.values()), "by_source": by_source, "dim": _configured_dim()}
    except Exception as e:
        logger.warning("[vector_store] stats error uid=%s: %s", uid, e)
        return {"total": 0, "by_source": {}, "dim": _configured_dim()}
    finally:
        db.close()


def list_entries(uid: str, char_id: str, *, source: str | None = None,
                 limit: int = 100, offset: int = 0) -> list[dict]:
    """浏览 vec_meta，按 ts 倒序（新→旧）。fail-open → []。"""
    db = _open_db(uid, char_id)
    if db is None:
        return []
    try:
        _ensure_tables(db, _configured_dim())
        if source:
            rows = db.execute(
                "SELECT rowid, source, source_id, ts, text_preview FROM vec_meta"
                " WHERE source = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
                (source, limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT rowid, source, source_id, ts, text_preview FROM vec_meta"
                " ORDER BY ts DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [{"rowid": r[0], "source": r[1], "source_id": r[2],
                 "ts": r[3], "text_preview": r[4] or ""} for r in rows]
    except Exception as e:
        logger.warning("[vector_store] list_entries error uid=%s: %s", uid, e)
        return []
    finally:
        db.close()
```

### 1.2 `admin/routers/observe.py` 新增 3 个路由

放在文件末尾，紧跟现有 `/observe/...` 路由风格（`tags=["观测"]`、`Depends(verify_token)`）。
char_id 解析直接复用 provenance 里现成的：`from admin.routers.provenance import _resolve_char_id`。
uid 列表复用 users 里现成的：`from admin.routers.users import _get_known_users`。

也更新文件顶部 docstring，补三行 `GET /observe/vector...` 说明。

```python
@router.get("/observe/vector", summary="列出有向量库的 uid", tags=["观测"])
async def list_vector_uids(auth=Depends(verify_token)):
    from admin.routers.users import _get_known_users
    return {"uids": _get_known_users()}


@router.get("/observe/vector/{uid}", summary="向量库统计 + 条目浏览", tags=["观测"])
async def get_vector_overview(uid: str, source: str = "", limit: int = 100,
                              char_id: str = "", auth=Depends(verify_token)):
    from core.memory import vector_store as vs
    from admin.routers.provenance import _resolve_char_id
    cid = _resolve_char_id(char_id)
    lim = min(max(limit, 1), 500)
    return {
        "uid": uid, "char_id": cid,
        "stats": vs.stats(uid, cid),
        "entries": vs.list_entries(uid, cid, source=source or None, limit=lim),
    }


@router.get("/observe/vector/{uid}/search", summary="向量库语义检索", tags=["观测"])
async def search_vector(uid: str, q: str, k: int = 8, source: str = "",
                        char_id: str = "", auth=Depends(verify_token)):
    from core.memory import vector_store as vs
    from core.memory import embedding
    from admin.routers.provenance import _resolve_char_id
    cid = _resolve_char_id(char_id)
    if not q.strip():
        return {"uid": uid, "char_id": cid, "query": q, "results": []}
    vecs = await embedding.embed([q])
    if not vecs:
        return {"uid": uid, "char_id": cid, "query": q, "results": [], "error": "embed_failed"}
    hits = vs.query_with_preview(uid, cid, vecs[0], min(max(k, 1), 50),
                                 sources=[source] if source else None)
    return {
        "uid": uid, "char_id": cid, "query": q,
        "results": [{"source_id": sid, "preview": prev,
                     "distance": dist, "similarity": vs.dist_to_sim(dist)}
                    for sid, prev, dist in hits],
    }
```

> `/provenance/{uid}` 已存在，**Part 1 不动它**，前端直接用。

---

## Part 2 — 前端：侧边栏重排 + 分类折叠

文件：`admin/static/index.html`。

### 2.1 替换导航块（约 288–311 行）

把现有的 `🎭 叶瑄` 标签那行 **删除**；把四段「标题 div + 链接」重写成「可折叠分组」。
**保留每个 `<a>` 的 `data-page` / `onclick` / icon / 文案完全不变**，只是套进分组容器、并把两个分类标题改写为可点击的 header（原「观测/调试」→ 拆成「内部状态」+「观测」）。

```html
<div class="nav-group-header" onclick="toggleNavGroup('create')"><span class="nav-caret" id="caret-create">▾</span>🎨 创作</div>
<div class="nav-group" id="navgroup-create">
  <a data-page="character"      onclick="goto('character')">      <span class="icon">🃏</span>角色卡</a>
  <a data-page="lorebook"       onclick="goto('lorebook')">       <span class="icon">🌍</span>现实设定</a>
  <a data-page="dream-settings" onclick="goto('dream-settings')"> <span class="icon">🌙</span>梦境设定</a>
</div>

<div class="nav-group-header" onclick="toggleNavGroup('ops')"><span class="nav-caret" id="caret-ops">▾</span>🛠 运维</div>
<div class="nav-group" id="navgroup-ops">
  <a class="active" data-page="status" onclick="goto('status')"><span class="icon">📊</span>系统状态</a>
  <a data-page="scheduler" onclick="goto('scheduler')"><span class="icon">⏰</span>调度器</a>
  <a data-page="users"     onclick="goto('users')">    <span class="icon">👤</span>用户管理</a>
  <a data-page="logs"      onclick="goto('logs')">     <span class="icon">📋</span>错误日志</a>
</div>

<div class="nav-group-header" onclick="toggleNavGroup('state')"><span class="nav-caret" id="caret-state">▾</span>🔬 内部状态</div>
<div class="nav-group" id="navgroup-state">
  <a data-page="observe-mood"    onclick="goto('observe-mood')">   <span class="icon">🌸</span>情绪·花园</a>
  <a data-page="observe-dream"   onclick="goto('observe-dream')">  <span class="icon">🌙</span>梦境状态</a>
  <a data-page="observe-memory"  onclick="goto('observe-memory')"> <span class="icon">🧠</span>记忆探查</a>
  <a data-page="observe-hidden"  onclick="goto('observe-hidden')"> <span class="icon">🔬</span>隐性状态</a>
  <a data-page="observe-chatlog" onclick="goto('observe-chatlog')"><span class="icon">💬</span>聊天日志</a>
  <a data-page="observe-runtime" onclick="goto('observe-runtime')"><span class="icon">⚙️</span>运行时内部态</a>
</div>

<div class="nav-group-header" onclick="toggleNavGroup('observe')"><span class="nav-caret" id="caret-observe">▾</span>🔍 观测</div>
<div class="nav-group" id="navgroup-observe">
  <a data-page="observe-prompt"  onclick="goto('observe-prompt')"> <span class="icon">🗂️</span>Prompt 层检视</a>
  <a data-page="observe-probe"   onclick="goto('observe-probe')">  <span class="icon">🔭</span>探针观测</a>
  <a data-page="observe-dream-prompt" onclick="goto('observe-dream-prompt')"><span class="icon">💭</span>梦境 Prompt</a>
  <a data-page="observe-trigger-catalog" onclick="goto('observe-trigger-catalog')"><span class="icon">📡</span>触发器目录</a>
  <a data-page="observe-vector"     onclick="goto('observe-vector')">    <span class="icon">🧬</span>向量库</a>
  <a data-page="observe-provenance" onclick="goto('observe-provenance')"><span class="icon">🧾</span>印象溯源</a>
</div>
```

> 第 314 行那两个 `style="display:none"` 的隐藏链接（`pet` / `yexuan`）保持原样，放在最后一个分组之后即可。
> 删掉 `#nav-char-label` 元素是安全的：约 1299 行的 `querySelectorAll('#nav-char-label, .nav-char-name, #page-char-name')` 找不到它会自动跳过，不报错，`.nav-char-name` / `#page-char-name` 仍正常更新。

### 2.2 CSS（加到 `<style>` 里）

```css
.nav-group-header{padding:8px 20px 2px;font-size:11px;color:var(--muted);letter-spacing:.05em;text-transform:uppercase;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.nav-group-header:hover{color:var(--text)}
.nav-caret{display:inline-block;font-size:9px;width:10px}
```

### 2.3 折叠 JS（加到脚本区，比如紧挨 `goto` 附近）

```js
function toggleNavGroup(key){
  const g=document.getElementById('navgroup-'+key), c=document.getElementById('caret-'+key);
  if(!g) return;
  const willShow = g.style.display==='none';
  g.style.display = willShow?'':'none';
  if(c) c.textContent = willShow?'▾':'▸';
  const st=JSON.parse(localStorage.getItem('navGroupsCollapsed')||'{}');
  st[key]=!willShow;                       // true=已折叠
  localStorage.setItem('navGroupsCollapsed',JSON.stringify(st));
}
function restoreNavGroups(){
  const st=JSON.parse(localStorage.getItem('navGroupsCollapsed')||'{}');
  for(const key of ['create','ops','state','observe']){
    if(st[key]){
      const g=document.getElementById('navgroup-'+key), c=document.getElementById('caret-'+key);
      if(g) g.style.display='none';
      if(c) c.textContent='▸';
    }
  }
}
```

登录成功、`#app` 显示出来之后调用一次 `restoreNavGroups()`（放在现有「显示主界面 + 首次 `loadStatus()`」那段逻辑里）。

---

## Part 3 — 前端：两个新观测页

两页都加到 `<main>` 里（紧接现有 `page-observe-trigger-catalog` 之后），并在 `goto()` 的 `loaders`
映射里注册。复用现成的 `api('GET', path)`、`escapeHtml()`、`togglePromptLayer()`、`.card`、`.btn` 等。
uid 选择器：两页都先 `api('GET','/users')` 拉用户列表填下拉框（参考其它观测页拿 uid 的方式）。

### 3.1 印象溯源（`observe-provenance`）

**页面骨架：**
```html
<div class="page" id="page-observe-provenance">
  <h1 class="page-title">印象溯源 <span style="font-size:13px;font-weight:400;color:var(--muted)">只读 · 每条概括何时·因何·从哪条聊天记录改动</span></h1>
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
    <select id="prov-uid" class="input" style="max-width:180px"></select>
    <input id="prov-artifact" class="input" placeholder="artifact（如 identity，可空）" style="max-width:200px">
    <input id="prov-field" class="input" placeholder="field（如 trust_pattern，可空）" style="max-width:200px">
    <label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px"><input type="checkbox" id="prov-scope"> 仅叶瑄自身漂移</label>
    <button class="btn btn-ghost btn-sm" onclick="loadProvenance()">查询</button>
  </div>
  <div id="prov-content"></div>
</div>
```

**loader（参考 `loadTriggerCatalog` 的卡片渲染 + `togglePromptLayer` 折叠）：**
- 切页时若下拉为空，先填 uid 列表（`/users`），默认选第一个，然后 `loadProvenance()`。
- 请求：`/provenance/{uid}?artifact=&field=&scope=&limit=100`（scope 勾选时传 `scope=yexuan_self`）。
- 每条 record 渲染一张卡：
  - 顶行：`new Date(ts*1000)` 格式化时间 + `artifact · field` 徽章 + `trigger_signal`。
  - 主体：`before_gist` → `after_gist`（用箭头/不同颜色区分）。
  - **`origin`（核心：从哪条聊天记录总结来的）**：是个对象，默认折叠，点开用 `<pre>` 显示
    `JSON.stringify(origin, null, 2)`（沿用 trigger-catalog 里 `togglePromptLayer(contentId)` 的展开方式）。
- 空结果显示「该 uid 暂无溯源记录（日志从接入当日起前向积累）」。

### 3.2 向量库（`observe-vector`）

**页面骨架：**
```html
<div class="page" id="page-observe-vector">
  <h1 class="page-title">向量库 <span style="font-size:13px;font-weight:400;color:var(--muted)">只读 · sqlite-vec 语义索引</span></h1>
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">
    <select id="vec-uid" class="input" style="max-width:180px"></select>
    <select id="vec-source" class="input" style="max-width:160px"><option value="">全部 source</option></select>
    <button class="btn btn-ghost btn-sm" onclick="loadVector()">刷新</button>
  </div>
  <div id="vec-stats" style="margin-bottom:12px"></div>
  <div style="display:flex;gap:8px;margin-bottom:12px">
    <input id="vec-q" class="input" placeholder="语义检索：输入一句话，找最相近的记忆…" style="flex:1">
    <button class="btn btn-ghost btn-sm" onclick="searchVector()">检索</button>
  </div>
  <div id="vec-content"></div>
</div>
```

**loader：**
- 切页填 uid 下拉（`/users`），默认第一个 → `loadVector()`。
- `loadVector()`：请求 `/observe/vector/{uid}?source=&limit=100`。
  - 顶部 `#vec-stats` 显示 `stats`：总条数 `total`、维度 `dim`，以及 `by_source` 各来源计数（小徽章，如 `episodic 42`、`event_log 88`、`web 5`）。同时用 `by_source` 的 key 填充 `#vec-source` 下拉选项。
  - `#vec-content` 列出 `entries`：每行 `source` 徽章 + `source_id` + 时间(`ts`) + `text_preview`（截断 + 可点开看全文，沿用 togglePromptLayer）。
- `searchVector()`：取 `#vec-q`、`#vec-source`，请求 `/observe/vector/{uid}/search?q=&k=8&source=`，结果按 `similarity` 高→低渲染（显示 similarity 百分比 + source_id + preview）；`error: embed_failed` 时提示「嵌入模型未配置或调用失败」。

### 3.3 在 `goto()` 的 `loaders` 映射里登记

```js
'observe-vector':     () => loadVector(),
'observe-provenance': () => loadProvenance(),
```
（首次切页内部自行拉 uid 列表即可，不必预热。）

---

## 验收清单

1. 侧边栏不再有 `🎭 叶瑄`，四个分组标题（创作/运维/内部状态/观测）各自点击能折叠/展开，刷新页面后折叠状态保持。
2. 「内部状态」含 6 项（情绪·花园…运行时内部态）；「观测」含 6 项（Prompt 层检视、探针观测、梦境 Prompt、触发器目录、向量库、印象溯源）。
3. 印象溯源页能选 uid、按 artifact/field/scope 过滤，能展开每条的 `origin` 看到来源聊天记录。
4. 向量库页显示总数 + 各 source 计数 + 条目列表；语义检索能返回按相似度排序的结果。
5. 切其它老页面、登录流程、角色名显示均不受影响。

## 注意事项（项目硬规则）

- 所有 `data/` 路径走 `core/sandbox.get_paths()`——本次后端 helper 已通过 `vector_store._db_path` 间接满足，**不要硬编码路径**。
- 新增接口全部**只读 + fail-open**，绝不可影响写入主链路。
- 改完 `admin/static/index.html`：纯前端，无对应 doc。改完 `observe.py` / `vector_store.py`：相关 doc 是 `docs/vector-store.md`——在其中补一节「只读观测接口 `/observe/vector*`」即可满足 doc-sync Stop 钩子；若钩子仍拦，明确声明「no doc update needed: 纯前端/已更新 vector-store.md」。
- `tag_rules.py` 没动，无需跑 `tests/run_eval.py`。改完跑一下 `pytest` 冒烟，确认没 import 报错。

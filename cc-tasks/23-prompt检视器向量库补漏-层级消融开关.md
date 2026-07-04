# CC 任务 23 · Prompt 检视器向量库补漏 + 层级消融开关

> 背景：管理面板 prompt 层检视器（`core/observe/prompt_capture.py` + `admin/routers/observe.py` + `admin/static/index.html` 观测页）本体是通用的——凡带 `_layer` 的消息都会自动出现，无整层遗漏。但 X2/X3 向量库召回链路的**溯源信息**有缺口，且缺一套按层消融开关。
> 本任务分 A（补漏）、B（消融开关）两部分。所有行号已对照当前源码核实。
>
> 决策已定：消融开关**只过滤注入，不短路检索**（fetch_context 照常跑，保证改动面最小；消融结论一样准，因为 LLM 看到的 prompt 是唯一变量）。recall_trace 面板入口和 perception_block 子开关**本次一并做**。

---

## A. 检视器补漏（向量库溯源）

### A1. `web_recall` 层补 `_provenance`【改代码】

**根因**：`core/prompt_builder.py:979` 附近 web_recall 层消息没有 `_provenance`，`prompt_capture.capture()` 对无 provenance 的层推断为 `{"mode":"always"}` → 面板显示"常驻"。实际它是向量库 X3 语义召回（`pipeline.py:431` 起，`vs.query_with_preview(sources=["web"], k=3)`），召回 query 和命中明细全部不可见。

**修法**：
1. `build_prompt()` 签名新增可选参数 `web_recall_hits: list | None = None`（形如 `[(url, dist), ...]`）。
2. `core/pipeline.py` X3 块里收集 `[(u, round(d, 4)) for u, _p, d in _web_hits]`，与 `web_recall_result` 一起放入 fetch_context 返回 dict（键 `web_recall_hits`），`build_prompt()` 调用处（pipeline.py:561 附近）传入。
3. web_recall 层消息加：
   ```python
   "_provenance": {
       "mode": "scored",
       "rag_query": user_message[:200],
       "source": "vector_store:web",
       "hits": web_recall_hits or [],
   },
   ```
4. ⚠️ `core/observe/prompt_capture.py:capture()`（约 70-80 行）目前只复制 provenance 的 4 个固定键（mode/triggers_checked/matched_tags/rag_query），要补透传 `source`、`hits`（或改为白名单浅拷贝，白名单加这两个键）。
5. 前端 `_provDetail()`（index.html:3310 附近）scored 分支追加渲染 `source` 与 `hits`（URL + 距离，每行一条）。

### A2. recall_trace 补写向量命中【改代码】

**根因**：`core/pipeline.py:413` 的 `_write_recall_trace()` 只写 episodic/event_log/lore 命中。X2 的 `_semantic_hits`（pipeline.py:267，`vs.query(k=8)`，喂给 event_log.search 和 episodic.retrieve 的向量通道）与 X3 的 web 命中都没落 trace → 无法判断 6b/6c 内容来自关键词还是向量通道。

**修法**：
1. trace dict 增加两个键：
   - `"semantic_hits": [(id, round(dist,4)) for id, dist in _semantic_hits]`（X2 原始命中）
   - `"web_recall_hits": ...`（A1 收集的列表）
2. ⚠️ **代码顺序**：当前 X3 块（pipeline.py:431 起）在 recall_trace 写入（pipeline.py:410）**之后**执行。把 recall_trace 写入块整体移动到 X3 块之后，才能带上 web_recall_hits。

### A3. recall_trace 观测端点 + 面板卡片【新增】

**根因**：`core/recall_trace.py` 落盘到 `data/runtime/memory/{char_id}/{uid}/recall_trace/{date}.jsonl`，注释写着 "read by future GET /debug/recall endpoint"——一直没建，面板无入口。

**修法**：
1. `admin/routers/observe.py` 新增：
   ```
   GET /observe/recall/{uid}?date=YYYY-MM-DD&n=5   # date 缺省=今天，n=尾部条数
   ```
   scope 用 `require_scopes("memory.read")`（与同文件其它观测端点一致）。路径解析复用 `MemoryScope.reality_scope(uid, char_id)` + `resolve_path(scope, "recall_trace")`（与 recall_trace.py 写入侧同源），char_id 用 `admin/routers/provenance.py::_resolve_char_id` 的现成逻辑。文件不存在返回 `{"records": []}`，不 404。
2. `admin/static/index.html` 观测页：prompt 检视器卡片下方新增「召回溯源」卡片，复用同一个 uid 输入框；每条记录渲染 ts / query / episodic_hits / event_log_hits / lore_hits / semantic_hits / web_recall_hits / mood，折叠展开样式抄 prompt 层卡片。

### A4. 文档漂移修复【改文档】

`docs/prompt-layers.md`：
1. 层总览表**缺三行**：`5.1_user_facts`（prompt_builder.py:791）、`web_recall`（:979）、`11.7_pinned_facts`（:1309）。按代码补齐触发条件与数据来源。
2. `_drop_priority` 裁剪顺序表缺 `web_recall`（35，介于 3.9_screen_awareness=25 和 6b_event_search=30 之间——注意表按数值排序插入正确位置）。
3. 本任务 B 部分完成后，同文件新增「层级消融开关」章节（见 B8）。

---

## B. 层级消融开关（对比 / 消融测试用）

### 设计要点

- **单一改动点**：不在 40 多个 if 块里各加判断，而是在 build_prompt **组装完成后、token 估算与裁剪之前**统一过滤。这样字符估算、裁剪、capture 快照全部反映消融后的真实 prompt。
- **只过滤注入**：fetch_context / 检索照常执行（已确认的决策）。
- **全局开关**（单用户系统），进程内热生效，无需重启。
- fail-open：开关文件缺失/损坏 = 全部启用。

### B1. 开关存储

`core/data_paths.py` 新增方法（仿 `active_prompt_assets()`，:320）：

```python
def prompt_layer_ablation(self) -> Path:
    """Runtime config: data/runtime/prompt_layer_ablation.json"""
    return self._p("runtime", "prompt_layer_ablation.json")
```

文件格式：

```json
{
  "disabled_layers": ["5.5_lore", "6b_event_search"],
  "perception_block_disabled": false,
  "updated_at": "2026-07-04T12:00:00"
}
```

硬规则 1：一切经 `core/sandbox.get_paths()`，不许硬编码路径。

### B2. `core/prompt_ablation.py` 新模块

```python
ALWAYS_ON = {"1_system_prompt", "12_user_message"}   # 不可消融

def get_state() -> dict          # {"disabled_layers": set(), "perception_block_disabled": bool}
def set_state(disabled: list[str], perception_block_disabled: bool) -> dict
```

- 进程内缓存 + 文件 mtime 失效检查（每次 get_state 比对 mtime，变了才重读）。
- 读失败（不存在 / JSON 损坏）→ 返回全启用默认值，log warning，**绝不 raise**。
- set_state 原子写（tmp + os.replace），写后刷新缓存。
- set_state 内校验：`disabled ∩ ALWAYS_ON` 非空 → raise ValueError（路由层转 422）。

### B3. build_prompt 统一过滤点

位置：`core/prompt_builder.py` 组装完 `12_user_message`（:1329）之后、token 估算（:1360 附近 `token_estimate` 计算）**之前**：

```python
from core.prompt_ablation import get_state as _ablation_state
_ab = _ablation_state()
_ablated_layers: list[str] = []
if _ab["disabled_layers"]:
    _keep = []
    for _m in messages:
        _lyr = _m.get("_layer", "")
        if _lyr in _ab["disabled_layers"] and _lyr not in ALWAYS_ON:
            _ablated_layers.append(_lyr)
        else:
            _keep.append(_m)
    messages = _keep
```

- `debug_info` 增加 `"ablated_layers": _ablated_layers`（同名多条消息如 `7_mes_example_item`、`9_history` 会出现重复项，保留重复以便看到移除条数）。
- `_layers` 列表（layers_activated）不必回改——快照里 activated 与 ablated 并列展示即可。
- 已知联动（写进 B8 文档）：
  - `6c_episodic_fallback` 的消息 `_layer` 写的是 `6c_episodic`（prompt_builder.py:884，文档 :35 已注明）→ 关 `6c_episodic` 会连 fallback 一起关，**预期行为**。
  - `9_history` 允许关（消融场景需要），前端标红警示。
  - 破限层（0/2/11_jailbreak）已有 jailbreak_entries 的 enabled 管理，这里仍纳入统一开关（双闸，任一关即不注入）。

### B4. perception_block 子开关

perception_block 不是独立消息（嵌在 1_system_prompt 的 `{perception_block}` 槽位，prompt_builder.py:363-382，文档 :112 注明无独立 `_layer`）。在 :363 处：

```python
perception = perception_block.strip() if perception_block else ""
if _ab["perception_block_disabled"]:
    perception = ""
```

（`_ab` 的读取提前到函数体前部一次性完成，B3 复用同一个结果，避免读两次。）

### B5. capture 快照标注

`core/observe/prompt_capture.py::capture()`：snap 顶层增加 `"ablated_layers": meta.get("ablated_layers", [])`。被消融的消息已不在 messages 里，所以只做顶层列表展示（与 `removed_layers` 并列），不逐层打标。

### B6. API（放 `admin/routers/settings_misc.py`，仿 context-config）

```
GET /prompt-ablation    → {"known_layers": [...], "always_on": [...],
                            "disabled_layers": [...], "perception_block_disabled": bool}
PUT /prompt-ablation    body: {"disabled_layers": [...], "perception_block_disabled": bool}
```

- scope 与同文件 context-config 一致：`require_scopes("admin")`。
- PUT 校验：未知层名 → 422（用 known_layers 校验）；含 ALWAYS_ON → 422。
- `known_layers` 来源：`core/prompt_builder.py` 顶部新增常量 `KNOWN_LAYERS`——`[(层名, 一句话说明)]`，覆盖全部 `_layer` 字面量（含 `web_recall`、`dream_afterglow_soft_hint`、`11.7_pinned_facts` 等，特殊条目 `perception_block` 不放这里，由独立字段表达）。
- **防漂移测试**：新增测试扫描 prompt_builder.py 源码中所有 `"_layer": "..."` 字面量，断言 ⊆ KNOWN_LAYERS 名称集合（`6c_episodic_fallback` 写入的 `6c_episodic` 天然被覆盖）。

### B7. 前端（index.html 观测页）

1. prompt 检视器卡片上方或旁边新增「层级开关（消融测试）」卡片：
   - GET /prompt-ablation 渲染全部 known_layers，每层一个 toggle + 说明；ALWAYS_ON 灰置不可点；`9_history` 关闭时行内红字警示"关闭短期历史将严重改变行为"。
   - perception_block 单独一行 toggle。
   - 「保存」按钮 → PUT，成功后 toast"已生效，下一轮对话起作用"。
2. 快照视图 summary 区：`ablated_layers` 非空时显示紫色徽标行「已消融层：…」，与红色"被裁层"并列。

### B8. 文档同步（doc sync hook 会拦，必须做）

- `docs/prompt-layers.md` 新增「层级消融开关」章节：机制（组装后过滤、检索不短路）、ALWAYS_ON、6c fallback 联动、perception_block 子开关、API、文件路径。
- 同文件顺带完成 A4 的漂移修复。
- `AGENTS.md` 关键文件速查表加一行 `core/prompt_ablation.py`。

### B9. 测试 `tests/test_prompt_ablation.py`

1. 关 `5.5_lore` → build_prompt 输出无该层消息，`debug_info["ablated_layers"]` 含它。
2. 关 `6c_episodic` → episodic 与 fallback 消息均不出现。
3. `set_state(["1_system_prompt"], ...)` → ValueError；PUT 层面 422。
4. 开关文件写入损坏 JSON → get_state 返回全启用，不 raise。
5. `perception_block_disabled=True` → 1_system_prompt 内容不含感知段。
6. 全开状态（默认文件缺失）→ 输出与改动前完全一致（回归保护）。

不动 `tag_rules.py` → 无需跑 `run_eval.py`。改完全量 `pytest` 验证。

---

## 验收清单

- [ ] 面板 web_recall 层显示"打分召回"徽标 + 召回 query + 命中 URL/距离
- [ ] recall_trace JSONL 含 `semantic_hits` / `web_recall_hits`；观测页「召回溯源」卡片可查
- [ ] 关任意非 ALWAYS_ON 层：下一轮生效，快照出现「已消融层」徽标，token 估算随之下降
- [ ] ALWAYS_ON 层在面板灰置、API 拒绝
- [ ] 全开时输出与现状逐字节一致（测试 6）
- [ ] `docs/prompt-layers.md` 三处漂移已补 + 新章节；pytest 全绿

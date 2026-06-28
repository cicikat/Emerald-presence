# TOY-IMPL · 叶瑄自主写入沙盒（veryformalproject / 自生长数据库雏形）

> 后端（Emerald-presence）。诊断已查清，本工单是「补自主路径」。与 X3（自己上网/自建库）同源，存储未来复用 X1 `vector_store`。
> **改造档位：新增自主写入触发**，不改现有 toybox 读写/沙盒逻辑（那部分是好的）。

## 诊断结论（已核实）

`core/tools/toybox.py` 完整可用：3 个白名单文件（`思考笔记.txt` / `愿望清单.md` / `涂鸦板.txt`）在 `data/very_formal_project/` 下，4000 字上限、沙盒越界防护、overwrite/append。`read_toy_file`/`write_toy_file` 已注册（`tool_dispatcher.py:733-780`）。

**为什么叶瑄"没动过"**（两层原因）：

1. **纯反应式**：全仓除工具注册外**无任何自主调用** `write_toy_file` 的代码。只能靠用户消息命中探针（examples「读一下思考笔记」等）才触发——叶瑄从不**主动**写。
2. **模式受限**：`category: "desktop"` 落在 `tool_dispatcher.py:158 _MODE_RESTRICTED_CATEGORIES={"desktop","system"}`，QQ 模式下根本不可用。

即：当前是个**手动玩具**，不是「自生长数据库」。要跑通自生长，缺的是**自主写入触发**。

## 目标（MVP：让它自己长起来）

让叶瑄在有值得记的东西时，**自行**往沙盒追加一笔，受控、限频。先不追求智能，先让"自主写入"这条路真的跑起来。

## 改动点

### 1. 自主写入触发（核心，走慢队列/post_process，绕开探针与模式限制）

- 在 `core/post_process/`（或慢队列消费链）加一个 hook：每轮回复后**轻量判定**「这轮有没有值得叶瑄记进思考笔记的东西」。
  - 判定用一次 lightweight LLM（category 复用 `summary`/`consolidation` 档，10–30s），prompt：给定本轮对话，输出「要记的一句话」或空。空则不写。
  - 命中 → `write_toy_file("diary", 一句话, mode="append")`（思考笔记是叶瑄的随手记）。
  - **服务端直接调 toybox 函数**，不经探针、不受 desktop 模式限制（自主写入是系统行为，QQ 模式也该长）。
- **限频**：每个角色/用户每 N 小时最多自主写一次（配置 `toy_autogrow.min_interval_hours`，默认 6）；4000 字上限到顶后**滚动**（保留尾部，或归档另起）——别让 append 撞上限就报错。

### 2. 配置开关

```yaml
toy_autogrow:
  enabled: true
  min_interval_hours: 6
  target: diary          # 自主写入落到哪个白名单文件
```
关掉则退回纯手动玩具，行为同现状。

### 3.（Phase 2，依赖 X1）接入向量库，闭环"自检索"

自主写入的同时 `vector_store.upsert(uid, char_id, source="toy", source_id=..., ts, text)`，让叶瑄日后能**语义检索自己写过的东西**——这就是「自生长数据库」闭环，也是 X3 的本地半。**本工单先做 1+2（自主写入跑通）**，Phase 2 等 X1 落地后接，单列。

## 验收

1. 开 `toy_autogrow`，喂几轮有信息量的对话 → `data/very_formal_project/思考笔记.txt` **自动长出**新行，且符合 min_interval 限频。
2. 无信息量的闲聊轮 → 不写（判定返回空）。
3. QQ 模式下也能自主写入（证明绕开了 desktop 模式限制）。
4. append 撞 4000 字上限 → 走滚动，不抛错。
5. 关掉开关 → 退回纯手动，原 `read_toy_file`/`write_toy_file` 探针路径不受影响。

## 与其他工单的关系

- **X3**（自己上网/自建库/自检索）：本工单是 X3 的「本地自建库」雏形，存储选型已被 X1 统一（sqlite-vec + `embed()`）。X3 决策备忘会把"网页检索结果"也 upsert 进同一套。
- **依赖**：Phase 2 依赖 X1（已落地，可排期）。

## 文档同步

`docs/` 新增或更新 toy/autogrow 说明；`AGENTS.md` 工具系统段补「toy 自主写入走 post_process，非探针」。

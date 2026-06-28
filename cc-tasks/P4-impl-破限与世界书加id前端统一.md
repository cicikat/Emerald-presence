# P4-IMPL · 破限条目 + 世界书条目加稳定 id，前端统一管理

> 跨仓：后端 Emerald-presence + 前端 Emerald-client。
> **前置**：无（独立项）。**可并行**：与所有其他工单无冲突，可任何时候开。
> **改造档位：加字段 + 前端归一**，不改注入语义。

## 现状（已核对）

- **破限条目**：`admin/routers/jailbreak_entries.py` 已 `import uuid`、有 `enabled` 等字段；注入侧 `prompt_builder._load_jailbreak` 按文件 `stem` + 条目 `layer/enabled/content` 读，**注入不依赖 id**。id 有无/是否稳定需核实并补齐。
- **世界书条目**：`core/lore_engine.py` `_normalize_entry` 有 `content/keywords/regex/insertion_order`，**无 id**。
- 后果：前端要稳定引用/排序/编辑/将来溯源某一条，没有稳定锚点。

## 目标

破限与世界书条目**都带稳定 id**（后端 schema + 持久化 + API 暴露），前端用**同一套组件**管理两者（按 id 增删改查/排序/启停），UI 风格统一。

## 改动点

### 后端

1. **世界书**：`lorebook.yaml` 条目 schema 加 `id`（uuid，缺失时加载/保存时**补发并回写**一次）；`_normalize_entry` 透传 id；admin lore 读写 API 暴露 id。
2. **破限**：确认 `jailbreak_entries` 每条有稳定 `id`（用已 import 的 uuid，缺失补发回写）；导出/导入 JSON 保留 id。
3. 两者 id **生成/补发逻辑一致**（同一个 helper），保证幂等：已有 id 不变，仅缺失补。
4. 注入侧不变（仍按 layer/keywords 命中），id 只为管理/引用/溯源用。

### 前端（Emerald-client）

> 读 client `AGENTS.md`；HTTP 走 Tauri command，集中在 `src/shared/api/`。

1. 抽一个**通用条目管理组件**（list + 增删改 + 启停 + 排序），破限 tab 和世界书 tab **复用**它，差异用 props/schema 配置（破限有 `layer`，世界书有 `keywords/insertion_order`）。
2. 列表项以**后端 id 为 key**，编辑/删除按 id 调后端，不再靠数组下标。
3. 两个 tab 视觉统一（同一套卡片/按钮/间距）。

## 验收

1. 旧 lorebook.yaml / 破限文件加载后，每条都获得稳定 id 并回写；重启 id 不变。
2. 前端破限/世界书两 tab 用同一组件，按 id 编辑/删除/排序正确。
3. 导出再导入，id 不丢、不重。
4. 注入行为与改造前一致（命中逻辑没动）。

## 文档同步
后端 `docs/backend-integration.md` 记两类条目的 id 字段与 API；前端 `docs/frontend-structure.md` 记通用条目组件。

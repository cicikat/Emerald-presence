# F2-IMPL · 窗口标题注入 + 叶瑄自主看内容（含冷却 + 前端开关）

> 跨仓：后端 Emerald-presence + 前端 Emerald-client。诊断见 `W0-诊断结论.md` §F2。
> 已核：sensor 链路健康——client 抓标题（`src-tauri/src/sensor/focus_window.rs` + `title_sanitizer.rs`），后端 schema 收 `focus.title_hint` / `screen.window_title` 且敏感窗口 fail-closed（`admin/routers/sensor.py:175-235`），`realtime_state` 原样存。**断点是 `_format_realtime_awareness` 故意不注入标题**（`prompt_builder.py:124` docstring）。
> 用户确认要做，且**升级了需求**（见下）。数据隐私沿用现有 fail-closed，不放松。

## 需求（用户定）

1. 让叶瑄重新「看到」当前窗口**标题**（如 Obsidian 文档名）。
2. 看到标题后，叶瑄**自己选择**要不要进一步翻看该窗口的**全文内容**。
3. **冷却**：同一个文件/窗口，N 分钟内只能触发一次「看内容」。
4. **开关 + 分钟数**放到**前端设置页**，用户可开关、可调 N。

---

## 后端改动（Emerald-presence）

### 1. 标题注入（恢复 §F2 断点）

`core/prompt_builder.py` `_format_realtime_awareness`（123-166）：在现有 app 摘要后，**追加一个 sanitized 标题片段**，取自 `snap["focus"]["title_hint"]`（已 server 端截断 80 字、过敏感窗口）。保持「短、旁白语气」。例如在 parts 里加：`在写《{title_hint}》` / `在看「{title_hint}」`。
**红线**：只用 `title_hint`；**绝不**在此处注入 `visible_text` / `clickable_text`（那是第 2 步受控工具的事）。

### 2. 新 info 工具 `peek_screen_content`（叶瑄自主看全文）

- 新增 `core/tools/screen_peek.py`：从 `realtime_state.get()` 读当前快照的 `screen.visible_text` / `clickable_text`（已截断、已过敏感窗口），拼成受控摘要返回。
- 注册进 `_TOOL_REGISTRY`，`category: "desktop"`，带 `examples`/`keywords`（如「看看她在写什么」「翻一下那篇内容」）。**它是叶瑄自主触发的**：探针在叶瑄"好奇"时调用——靠 author_note 给一句软提示「看到标题后如果在意，可以选择看看内容」，让模型自行决定是否调用，而非强制。
- **总开关**：工具入口先查配置 `screen_peek.enabled`；关则直接返回「未开启」，不读内容。

### 3. 冷却（同文件 N 分钟一次）

- 在 `screen_peek.py` 维护一个**内存** dict：`{file_key → last_peek_ts}`，file_key 取 `title_hint`（或 `window_title`）规范化后的值。
- 命中冷却（`now - last < N*60`）→ 工具返回「刚看过这篇，先不重复看了」，**不读内容、不刷新时间**；未命中 → 读内容并写 `last_peek_ts`。
- N 从配置 `screen_peek.cooldown_minutes` 读，默认 30。内存态，重启清零可接受。

### 4. 配置 + 管理端读写

- `config.yaml` 新增块：
  ```yaml
  screen_peek:
    enabled: false           # 默认关（用户在设置页打开）
    cooldown_minutes: 30
  ```
- 管理端补一个读写端点（沿用现有 settings 路由风格，如 `admin/routers/settings_*`）：`GET/POST /settings/screen-peek` 返回/更新 `enabled` 与 `cooldown_minutes`，供前端设置页调用。

---

## 前端改动（Emerald-client）

> 动手前读 client `AGENTS.md`。HTTP 走 Tauri command，别用浏览器 fetch（client 规则 7）。

- 在**设置页**（聊天设置 / Sidebar 设置面板，参照现有 chat-settings 接入方式）加一组控件：
  - 开关：「允许叶瑄查看屏幕内容」→ 绑 `screen_peek.enabled`。
  - 数字输入：「同一文件冷却（分钟）」→ 绑 `screen_peek.cooldown_minutes`，范围 5–240。
- 经 Tauri command 调后端 `GET/POST /settings/screen-peek`，集中在 `src/shared/api/`，别把 HTTP 散进组件（client 规则 3）。
- 开关说明文案点一句：开启后叶瑄可能主动提及你正在看/写的文件内容，关闭则只感知标题。让用户知情，避免「又被吓到」。

---

## 验收

1. 开关 **关**（默认）：叶瑄只提标题，调 `peek_screen_content` 返回「未开启」，绝不吐内容。
2. 开关 **开**：叶瑄能在在意时自主看一次内容并自然提起；同一文件 N 分钟内再次触发被冷却挡下。
3. 敏感窗口（命中 `_is_sensitive_window_text`）：标题与内容**都不**注入（沿用 sensor.py fail-closed）。
4. 前端改 `enabled`/`cooldown_minutes` 后，后端行为即时生效（无需重启）。
5. `visible_text`/`clickable_text` 永远只经 `peek_screen_content` 受控出口，别的注入层一律不碰。

## 文档同步

后端 `docs/backend-integration.md` 加 `/settings/screen-peek` 与 `peek_screen_content` 工具；`docs/known-issues.md` F2 标已修。前端 `docs/frontend-structure.md` 记设置页新控件。

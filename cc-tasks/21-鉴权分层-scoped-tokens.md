# Brief 21 · 鉴权分层 — Scoped Tokens（后端侧）

> 配对文档：`Emerald-client/cc-tasks/13-auth-scoped-tokens-client.md`（桌面客户端侧）、
> `yexuan_memery/cc-tasks/round-鉴权分层-scoped-tokens-移动端.md`（安卓端侧，其 §1 含对本文
> mobile profile 与 meta-mode 映射的两处增补——若本文施工时已合入下方表格则无需重复处理）。
> **必须先施工本文（后端）**，且 P1/P2 落地后旧 token 仍然全通，客户端侧可以延后任意久。
>
> 目标：把「一个 Bearer secret 过关后所有接口平权」的单层鉴权，升级为**多 token + scope 分层**。
> 核心收益不是防御桌面主客户端（它本来就是 owner 的可信全功能端），而是**收缩边缘设备的爆炸半径**：
> 手机 sensor-service、Watch、ESP32 固件、手机轮询端今天都持有 god token——其中任何一个设备丢失/被
> 拆机，等价于日记、隐性状态、危险模式开关、硬件控制全部泄露。改造后每个边缘设备只持有最小 scope token。

---

## 0. 现状盘点（事实，已核对代码）

- 鉴权唯一入口：`admin/auth.py` → `verify_token`（HTTP）/ `authenticate_ws`（WS）。
  单一 secret 来源：env `YEXUAN_ADMIN_SECRET` 或 `config.admin.secret_key`。
- 全部 ~35 个 router（`admin/routers/*.py`）的每个端点都是 `Depends(verify_token)`，无一例外
  （已 grep 验证：没有不带 verify_token 的 router）。两个 WS 端点（`/ws/desktop`、`/ws/device`）
  走 `authenticate_ws`，同一 secret。
- 服务绑定 `0.0.0.0:8080`（config.example.yaml），经 Tailnet 暴露给手机/Watch/板子。
- **同一个 secret 的持有者（=当前信任面）**：
  1. 桌面客户端（Emerald-client Tauri，`src-tauri/src/client_config.rs` → `admin_token`）
  2. 手机 sensor-service（`Emerald-client/sensor-service/config.yaml` → `backend.token`，明文）
  3. 手机轮询端（`/mobile/*`）
  4. Watch（`POST /watch/event`）
  5. ESP32 具身硬件（`/ws/device`，token 烧在固件配置里）
  6. 管理面板网页（`admin/static/index.html`，localStorage `qq_admin_key`）
- 该 token 可达的高危面（示例）：`PATCH /system/meta-mode`（安全/危险模式）、`/hardware/*`
  （Buttplug 实体硬件）、`PUT /llm-params` 等 settings 写、`POST /system/reload`、`/agent/think`、
  全部记忆/日记/隐性状态读、`POST /sensor/push`（可污染记忆的写入路径）。
- 已完成的前序安全轮（见 `docs/known-issues.md`）：SEC-AUTH-1（Bearer-only，去 query secret）、
  SEC-WS-1（WS 去 query token）。本 brief 是它们的续篇，编号 **SEC-AUTH-2**。

## 1. 设计总览

**目标**
1. 多 token：每个客户端/设备一个独立命名 token，可单独吊销、轮换。
2. Scope 分层：token 携带 scope 集合，端点声明所需 scope，**default-deny**。
3. 零破坏迁移：legacy secret（env / `config.admin.secret_key`）永远等价于 `admin` scope，
   P1~P3 期间所有现存客户端不改一行也能用。
4. 守卫测试保证「以后新增 router 忘了声明 scope」会直接 CI 失败，而不是静默放行。

**非目标（明确不做，防止过度工程）**
- 不做多用户/OAuth/JWT/session。单 owner 系统，opaque token + scope 足够。
- 不做 HTTPS（Tailnet 是 WireGuard 加密信道）。
- 不改 QQ/NapCat 通道（不走 admin HTTP 面）。
- 不在本轮做管理面板的 token 管理 UI（API 先行，UI 另开 brief）。

## 2. Scope 模型

10 个 scope。`admin` 蕴含全部（校验逻辑：`required ⊆ token.scopes or "admin" in token.scopes`）。

| scope | 语义 | 典型端点 |
|---|---|---|
| `admin` | 全权。settings 写、系统运维、token 管理、记忆写删 | `/system/reload`、`PUT /llm-params`、`/users/*`、`/agent/think` |
| `chat` | owner 对话回合 + 通道生命周期 + 上传/转写 | `/desktop/chat`、`/mobile/*`、`/desktop/wake|activate|deactivate`、`/upload/ingest`、`/transcribe`、`/group/*` |
| `state.read` | 低敏状态只读 | `/mood/state`、`/activity/current`、`/garden/state`、`/sensor/realtime`、`/watch/status`、`GET /status` |
| `memory.read` | 高敏内容只读 | `/diary/*`、`/chat-log/*`、`/history`、`/memory/*`（GET）、`/debug/user-hidden-state`、provenance/observe、relations（GET） |
| `sensor.write` | 感知数据写入（只写不读） | `POST /sensor/push`、`POST /sensor/activity`、`POST /watch/event` |
| `activity` | 活动/梦境 overlay 全生命周期 | `/dream/*`、`/activity/reading|gomoku|chess|dream_seed/*` |
| `persona` | 人设/世界/呈现配置读写 | `/settings/prompt-assets`、`/jailbreak-entries`、`/lorebook`、character 卡、`/chat-mode|chat-style|chat-multi-message`、头像 |
| `hardware` | 实体硬件控制 + 危险模式开关 | `/hardware/*`、`GET|PATCH /system/meta-mode` |
| `ws.desktop` | 连接 `/ws/desktop`（接收 action 推送） | WS |
| `ws.device` | 连接 `/ws/device` | WS |

**Profile（预置 scope 组合）**——建 token 时用 profile 名即可，定义为常量表：

| profile | scopes | 发给谁 |
|---|---|---|
| `desktop` | chat, state.read, memory.read, activity, persona, hardware, sensor.write, ws.desktop | 桌面 Tauri 客户端（sensor.write 因为它 POST `/sensor/realtime`、`/sensor/activity`） |
| `mobile` | chat, state.read, memory.read, activity, persona, sensor.write | 手机 Flutter 端（yexuan_memery；同为 owner 胖客户端，见其配对文档；刻意不含 hardware/admin——手机是最易丢失的设备，丢机不泄危险模式与 settings 写权） |
| `sensor` | sensor.write | 手机 sensor-service |
| `watch` | sensor.write | Watch |
| `device` | ws.device | ESP32 具身硬件 |
| `panel` | admin | 管理面板网页 |

> 桌面客户端确实需要 `hardware`（ToyWindow 轮询/连接设备、切换 meta-mode）和 `persona`
> （偏好面板「世界」页 patch prompt-assets）。它是胖客户端，这是有意的；分层的价值在边缘设备。

## 3. Token Registry

**存储**：`data/runtime/auth/tokens.yaml`。路径**必须**经 `core/sandbox.get_paths()` 新增访问器
（如 `get_paths().auth_dir()`），遵守硬规则 1；test 模式自动隔离。

```yaml
tokens:
  - label: desktop-main          # 唯一，人类可读
    hash: "sha256:9f2a…"         # sha256(token)，不存明文
    scopes: ["profile:desktop"]  # profile:* 或显式 scope 列表，可混用
    created_at: "2026-07-03T12:00:00+08:00"
    expires_at: null             # 可选
    disabled: false
```

- Token 明文格式：`emt_` + `secrets.token_urlsafe(32)`。前缀便于日志清洗与肉眼识别，仅创建时返回一次。
- 校验：对请求 token 求 sha256 后与全表比对，用 `hmac.compare_digest`；registry 常驻内存，
  文件 mtime 变化时热重载（模式抄 `core/config_loader.py`）。
- **Legacy 兼容**：`get_admin_secret()` 的值（env 优先）永远作为一条虚拟 admin token 参与校验，
  label 固定 `legacy-admin`。这是 bootstrap 锚点（否则没有 token 就无法调建 token 的 API）。
- 写入用 `core/safe_write.py` 原子写。

## 4. `admin/auth.py` 改造

```python
@dataclass
class TokenInfo:
    label: str
    scopes: frozenset[str]   # profile 已展开

def resolve_token(raw: str) -> TokenInfo | None: ...   # None = 无效

def require_scopes(*scopes: str):
    async def _dep(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenInfo:
        if not credentials:
            raise HTTPException(401, "Unauthorized")
        info = resolve_token(credentials.credentials)
        if info is None:
            _note_auth_failure(...)          # §7 限速
            raise HTTPException(401, "Unauthorized")
        if not _scopes_ok(info.scopes, scopes):
            _audit("scope_denied", label=info.label, need=scopes)   # §7 审计
            raise HTTPException(403, f"insufficient scope, need: {' '.join(scopes)}")
        return info
    _dep._required_scopes = scopes           # 守卫测试用标记，见 §8
    return _dep
```

- **`verify_token` 保留为 `require_scopes("admin")` 的别名**。这意味着 P1 合入后、P2 映射完成前，
  任何还没迁移的端点自动收敛为 admin-only —— **fail-closed**，漏改不产生安全洞（legacy secret
  仍是 admin，所以现存客户端不受影响）。
- 语义：无效/缺失 token → **401**；有效 token 但 scope 不足 → **403**（detail 里给出所需 scope，
  这个信息可公开）。客户端据此区分「token 配错」vs「权限不够」。
- WS：`authenticate_ws(websocket, required_scope: str) -> TokenInfo | None`。
  `/ws/desktop` 要求 `ws.desktop`，`/ws/device` 要求 `ws.device`（admin 照常蕴含）。
  两个 endpoint 在 `admin/admin_server.py` 改传 scope 参数。
- Token 值一如既往不得进入任何日志（`admin/log_filter.py` 的 sanitizer 已覆盖 access log；
  新增代码只允许记录 label 和 hash 前 8 位）。

## 5. 路由 → scope 映射表（P2 施工清单）

机械替换规则：把每个端点的 `Depends(verify_token)` 换成 `Depends(require_scopes(...))`，按下表。
「GET→X / 写→Y」表示同 router 内按 HTTP method 拆分。**表里没提的 router/端点一律
`require_scopes("admin")`**（default-deny）。

| router 文件 | scope |
|---|---|
| `chat.py` | chat（`POST /chat` 已禁用端点也标 chat，行为不变） |
| `mobile.py`、`group.py`、`transcribe.py` | chat |
| `mood.py`、`activity.py` | state.read |
| `garden.py` | GET → state.read；写 → admin |
| `sensor.py` | push/activity 写 → sensor.write；`GET /sensor/realtime` → state.read；其余 GET → state.read |
| `watch.py` | `POST /watch/event` → sensor.write；`GET /watch/status` → state.read |
| `diary.py`、`chat_log.py`、`hidden_state_debug.py`、`observe.py`、`provenance.py` | memory.read |
| `memory.py`、`relations.py`、`relationship_facts.py` | GET → memory.read；写/删 → admin |
| `dream.py`、`reading.py`、`gomoku.py`、`chess.py`、`dream_seed.py` | activity |
| `settings_prompt_assets.py`（含 `/settings/character-avatar/*`）、`jailbreak_entries.py`、`lorebook.py`、`character.py`、`settings_misc.py` 中的 chat-mode/chat-style/chat-multi-message 端点 | persona |
| `hardware.py` | hardware |
| `system.py` | `GET /status` → state.read；`GET /system/meta-mode` → state.read（手机能力检查页只读）；`PATCH /system/meta-mode` → hardware；其余（reload/logs/pet/group-distill/data-path）→ admin |
| `scheduler.py` | GET → state.read；PUT/POST → admin |
| `users.py`、`agent.py`、`settings_llm.py`、`settings_proxy.py`、`settings_screen_peek.py`、`settings_misc.py` 其余端点 | admin |

**校对步骤（必做）**：施工时在 Emerald-client 仓 grep `bearer_auth` 所在函数的 URL 常量，得到桌面
客户端实际调用的端点全集（已知包含 `/system/meta-mode`、`/scheduler/config`、`/settings/prompt-assets`、
`/jailbreak-entries`、`/lorebook`、`/memory/{uid}/short-term`（history 加载走这里）、`/chat-mode`、
`POST /sensor/realtime|activity` 等），
逐一确认落在 `desktop` profile 的 scope 并集内。若发现映射表遗漏，按最贴近的 scope 归类并在
PR 描述里注明，不得擅自归 admin 导致桌面端 403。

## 6. Token 管理 API（新 router：`admin/routers/auth_tokens.py`，全部 admin scope）

- `GET /auth/tokens` — 列表（label、scopes、created_at、expires_at、disabled、hash 前 8 位；无明文）。
- `POST /auth/tokens` — body `{label, profile 或 scopes, expires_at?}`；返回 token 明文**仅此一次**。
- `POST /auth/tokens/{label}/rotate` — 换新值，scope 不变，返回新明文一次。
- `DELETE /auth/tokens/{label}` — 吊销（物理删除或置 disabled 均可，选一种并写测试）。
- label 校验 `^[a-z0-9-]{1,32}$`；`legacy-admin` 为保留字，不可创建/删除。

## 7. 审计与失败限速

- **审计**：`data/runtime/auth/audit.jsonl` 追加（路径同样走 `get_paths().auth_dir()`；写失败
  fail-open，绝不阻塞请求）。记录事件：token 创建/轮换/吊销、401 失败（含来源 IP）、403 scope 拒绝、
  `PATCH /system/meta-mode` 切到 danger。字段：ts、event、label（或 "invalid"）、path、ip。**不记 token 值**。
- **限速**：进程内存 dict，按来源 IP 统计 401 次数；60s 窗口内 ≥10 次 → 该 IP 后续认证请求直接
  429，持续 300s。无外部依赖，重启清零即可接受。

## 8. 守卫测试（`tests/test_sec_auth2_scopes.py`，模式参考 `tests/test_sec_ws1_auth.py`）

1. **default-deny 全量扫描**：import `admin.admin_server.app`，遍历 `app.routes` 中所有 APIRoute
   （豁免名单：`/`、`/static/*`、`/docs`、`/openapi.json`、`/redoc`），递归检查 `route.dependant`
   的依赖链中存在带 `_required_scopes` 标记的 callable。任何裸端点 → 测试失败。
   这是本 brief 最重要的一条：它把「新增 router 忘记鉴权/忘记 scope」变成 CI 错误。
2. scope 语义：`chat` token 访问 `/diary/list` → 403；访问 `/desktop/chat` → 过鉴权层；
   `sensor.write` token GET `/sensor/realtime` → 403（只写不读成立）；`admin` token 全通。
3. legacy 兼容：`config.admin.secret_key` 的值命中任意端点均放行（等价 admin）。
4. 401/403 区分：坏 token → 401；scope 不足 → 403 且 detail 含所需 scope；token 值不出现在响应/日志。
5. WS：`ws.desktop` token 连 `/ws/device` 被拒（close 1008），反之亦然；admin 两个都能连。
6. 限速：同 IP 11 次坏 token 后 → 429。
7. token 管理 API：创建→用新 token 访问对应 scope 端点→rotate 后旧值失效→delete 后 401。

## 9. 施工分期与验收

每期独立可合入、可回滚：

- **P1 基座**：`core/sandbox` 新增 auth 路径访问器；token registry（加载/热重载/校验）；
  `require_scopes` + `verify_token`=admin 别名；WS scope 参数。
  验收：全测试绿；现存客户端（legacy secret）行为零变化。
- **P2 映射**：按 §5 全量替换 + 守卫测试 1~5。
  验收：`pytest` 绿；用桌面客户端（仍持 legacy secret）完整走一遍聊天/花园/日记/dream/toy 冒烟无 403。
- **P3 管理与加固**：auth_tokens router + 审计 + 限速 + 测试 6~7。
- **P4 发 token**（与客户端仓配对文档同步）：为六类持有者各建 token，边缘设备换装完成后
  轮换 legacy secret 的值（保留机制，只换值）。

## 10. 文档同步（Stop hook 会查）

- 新建 `docs/security.md`：鉴权模型、scope 表、profile 表、token 管理操作手册（创建/轮换/吊销）、
  审计文件位置。`AGENTS.md` 任务表加一行「改鉴权/token/scope → docs/security.md」，速查表加
  `admin/auth.py` 条目。
- `docs/known-issues.md` 增补 SEC-AUTH-2 条目（现状→已落地），链接本 brief。
- `config.example.yaml` 的 `admin.secret_key` 注释更新：说明它现在等价于 admin scope 的
  bootstrap token，边缘设备应使用 `/auth/tokens` 签发的最小权限 token。

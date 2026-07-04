# Brief 22 · DX — Token 管理页 + 本地密码本 + 首次配置引导

> 前置：Brief 21（SEC-AUTH-2 scoped tokens）已全部落地。本 brief 全部在本仓施工，
> 不动 Emerald-client / yexuan_memery 代码（只在文档里引用其配置路径）。
> 定位：开源项目的新用户/创作者体验。三块交付物：①`scripts/setup_auth.py` 首次配置 CLI、
> ②本地密码本（gitignored）+ rotate 命令清单文档、③管理面板 Token 管理页。

## 0. 设计决策（已拍板，施工不再讨论）

1. **没有 Show Token**：后端只存 sha256，明文结构性不可恢复。页面上明示这句话。
2. **不做「下载到密码本」**：浏览器够不着仓库文件。面板提供 [复制 Token] + [复制密码本条目]；
   「自动写进密码本」由服务端 CLI（setup_auth.py）完成。
3. **不做独立面板密码**：break-glass secret（`config.admin.secret_key` / env `YEXUAN_ADMIN_SECRET`）
   本来就可自定义，即"面板密码"。新增 `GET /auth/whoami` 让面板显示当前身份，仅此而已。
4. 密码本是**用户侧便利品**，后端永不读取它；它缺失/过期不影响任何功能。

## 1. 后端 API 增补（`admin/routers/auth_tokens.py`，全部 admin scope）

1. `PATCH /auth/tokens/{label}` body `{"disabled": true|false}` — 停用/启用。
   `legacy-admin` 保留字返回 422。写审计事件 `token_disabled` / `token_enabled`。
2. `GET /auth/whoami` — 返回 `{label, scopes}`。**任意有效 token 可调**（不要求 admin；
   用 `require_scopes()` 零参数依赖，仅验证 token 有效性——确认 `_scopes_ok` 对空 need 返回 True）。
3. `GET /auth/profiles` — 返回 profile→scopes 常量表（供 Create 下拉；admin scope）。
4. **核查项（可能是真洞）**：验证 `admin/token_registry.py` 的 `find_by_hash` / resolve 路径
   是否过滤 `disabled: true` 与 `expires_at` 已过期的记录。若没有 → 修复并补守卫测试
   （disabled token → 401；过期 token → 401）。无论核查结果如何，测试都要有。

## 2. `scripts/setup_auth.py` — 首次配置 CLI（DX 主路径）

直接 import 本仓模块操作 registry（参考现有 scripts/ 的写法），不走 HTTP，因此不需要已运行的后端。

行为（幂等，可反复跑）：

1. `config.admin.secret_key` 为空或等于示例占位值（`YOUR_ADMIN_SECRET`）→ 生成
   `secrets.token_urlsafe(32)` 写回 config.yaml（保注释的写法参考 `scripts/gen_config_example.py`
   或直接文本替换该行），并标记为"本次新生成"。
2. 六个标准 label（desktop-main / mobile-main / sensor-service / watch-main / esp32-device /
   admin-panel）逐个检查：不存在 → 创建；已存在 → 默认跳过，`--rotate-all` 参数时轮换。
3. 把所有本次拿到明文的 token + break-glass secret 写入 `secrets.local.yaml`（§3 格式）；
   已存在的密码本只更新对应条目，不覆盖用户自己加的内容（按 label 合并）。
4. 结尾打印面板引导块（也是"自动配置时显示登录 token"的实现）：

```text
✅ 鉴权初始化完成，凭据已写入 secrets.local.yaml（已 gitignore，勿提交）
🔑 管理面板: http://127.0.0.1:8080  →  登录 token 见密码本 admin-panel 条目
📋 各设备 token 的配置位置和轮换命令: docs/token-rotation.md
```

5. `main.py` 启动时若 secret_key 为空/占位且 registry 无任何 token → 控制台打印一行引导
   「首次使用请运行: python scripts/setup_auth.py」（不自动生成，不阻塞启动）。

## 3. 本地密码本 + 命令清单文档

**`secrets.example.yaml`**（提交进 git，占位符）→ 用户复制为 **`secrets.local.yaml`**
（加入 `.gitignore`；确认本仓有 .gitignore，没有则创建）。格式：

```yaml
# Emerald-presence 本地密码本 —— 明文凭据，永远不要提交 git。
# 轮换方法与完整说明: docs/token-rotation.md
break_glass_secret: "PLACEHOLDER"   # 面板应急登录 + token 管理的 bootstrap 凭据（= config.admin.secret_key）
tokens:
  desktop-main:   { token: "emt_PLACEHOLDER", 配置位置: "Emerald-client/config/client.local.json → adminToken" }
  mobile-main:    { token: "emt_PLACEHOLDER", 配置位置: "手机 app 系统设置 → Token 弹窗" }
  sensor-service: { token: "emt_PLACEHOLDER", 配置位置: "Emerald-client/sensor-service/config.yaml → backend.token" }
  watch-main:     { token: "emt_PLACEHOLDER", 配置位置: "Watch 端配置" }
  esp32-device:   { token: "emt_PLACEHOLDER", 配置位置: "固件配置（firmware/，烧录前写入）" }
  admin-panel:    { token: "emt_PLACEHOLDER", 配置位置: "浏览器面板登录框（localStorage qq_admin_key）" }
```

**`docs/token-rotation.md`**（新文档，命令行清单）内容：

- 每个 label 一节：作用、profile/scopes、**配置去向的精确路径**（同上表）、rotate 命令
  （PowerShell `Invoke-RestMethod` 和 curl 两版）、换装后需要重启什么（桌面端/后端/手机 app）。
- 通用段：401 vs 403 vs 429 含义；**rotate 后旧设备会刷 401、60s 内 10 次触发 429，
  重启后端可立即清限速**；break-glass secret 的修改方法（config.yaml / env）与保管建议；
  「面板无法显示已有 token 明文（只存哈希），丢了就 rotate」。
- `docs/security.md` 的操作手册章节改为链接本文档，避免两处维护。README 快速开始加一行
  指向 setup_auth.py。

## 4. 管理面板 Token 管理页（`admin/static/index.html` 新增 Tab「Token」）

沿用面板现有单文件风格与既有 fetch/token 约定（localStorage `qq_admin_key`）。

**表格列**：Label ｜ Scopes（profile 名 + 悬停展开实际 scope）｜ Status（●active / ○disabled /
◆legacy）｜ Created ｜ hash 前 8 位。数据源 `GET /auth/tokens` + `GET /auth/profiles`。
`legacy-admin` 虚拟行置顶展示，Status=◆break-glass，无操作按钮，悬停提示「修改：config.yaml
secret_key 或环境变量」。

**行按钮**：Rotate ｜ Disable/Enable（随状态切换）｜ Copy Label。表格上方：Create 按钮 +
一行说明文字「出于安全设计，已有 token 的明文无法再次查看（服务端只存哈希）；丢失请 Rotate」。

**Create 弹窗**：label 输入（前端校验 `^[a-z0-9-]{1,32}$`）+ profile 下拉（来自 /auth/profiles，
显示每个 profile 含的 scopes）。

**Rotate 确认弹窗**（文案照抄）：

```
⚠️ 将立即使旧 Token 失效。

持有旧 token 的设备会开始认证失败（401），
连续失败会触发 429 限速（重启后端可立即解除）。
请在 Rotate 后尽快更新对应设备的配置。

[取消] [Rotate]
```

**成功弹窗**（Create 与 Rotate 共用）：

```
新的 Token（仅显示一次）

emt_xxxxxxxxxxxxxxxxxxxx

[复制 Token] [复制密码本条目]
```

「复制密码本条目」复制一行可直接粘进 secrets.local.yaml 的 YAML：
`  <label>: { token: "emt_…", 配置位置: "<按 §3 表查 label，未知 label 用 '待填写'>" }`。
弹窗关闭需二次确认（「已保存好了吗？关闭后无法再查看」）。

**自我保护**：页面加载时调 `GET /auth/whoami`；对 Rotate/Disable 目标 == 当前登录 label 的操作，
确认弹窗附加红字「⚠️ 这是你当前登录面板使用的 token，操作后你需要用新值/break-glass 重新登录」。
Disable legacy-admin 不可能（无按钮），whoami 显示在页面右上角（「当前身份: admin-panel」）。

## 5. 测试与验收

1. 新端点测试：whoami（非 admin token 也可调）、PATCH disable→该 token 立即 401、
   enable 恢复、legacy-admin 422；§1.4 的 disabled/expired 过滤守卫测试。
2. `setup_auth.py`：空 config 全新跑 → secret 生成 + 六 token + 密码本齐全；重复跑幂等；
   `--rotate-all` 后密码本条目更新且旧值失效。
3. 守卫测试（Brief 21 的 default-deny 全量扫描）对新端点自动生效——确认仍绿。
4. 面板手工冒烟：Create → 新 token 能登对应 scope 端点；Rotate 流程文案与二次确认齐全；
   Disable 后该 token 401、Enable 恢复；「复制密码本条目」格式可直接粘贴；
   对自己 token 操作时出红字警告。
5. `secrets.local.yaml` 在 `.gitignore` 中且 `git status` 不显示；`secrets.example.yaml` 已提交。

## 6. 文档同步（Stop hook）

- 新建 `docs/token-rotation.md`（§3）；`docs/security.md` 操作手册章节改链接；
  README 快速开始加 setup_auth.py 一步；`AGENTS.md` 速查表加 `scripts/setup_auth.py` 与
  `admin/routers/auth_tokens.py` 两行。

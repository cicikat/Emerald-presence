# Brief 35 · 减法 Brief:Path B 降级 + 化石清理 + 静默失败可见化

> 来源:审计 §1.3 / §2.2 / §2.3 / §3.3 / §五,裁定见 docs/critique-triage-20260708.md。
> 这是本仓库第一个以"删"为主题的 brief。执行原则:删除必须连同其守卫、测试、文档条目
> 一起删——测试是跟随功能的,不是功能的遗产。

## 1. Path B 降级(两步走的第一步)

- 新增 config `intent_reflex.enabled: false`(**默认关**,现有用户升级即关)。
  `core/pipeline.py::_parse_and_execute_intent` 入口检查,关闭时直接 return。
- 五道守卫、c2 幂等窗口、keyword 校验**本步全部保留**(第二步整删时一起走)。
- docs/known-issues.md 登记观察项:"Path B 关闭期间,若出现'角色说了要做但没做'
  且探针/tool loop 均未覆盖的用户可感缺口,记录场景"。观察期一个月。
- 第二步(整删,含守卫+测试+文档)到期后单独出 brief,以观察记录为准,不预写。

## 2. 化石删除清单(审计 §2.2,逐项按引用计数执行)

执行顺序:每项先 grep 全仓引用 → 零真实调用者才删 → 删完跑全量 pytest。

| 化石 | 动作 |
|---|---|
| `scheduler.set_pipeline()` deprecated shim | `main.py:150` 调用点改直用 `pipeline_registry.register()`,然后删 shim。 |
| `slow_queue.LEGACY_TASK_TYPES` + `_handler_mid_term_append` 等 legacy handler | 先检查 DLQ 现存残留(工具/脚本查 `data/` 下 DLQ 存量):无残留 → 连注册带 handler 删;有残留 → 打印出来交用户决定(PR 里附清单)。 |
| `data_paths.py` 三个 `_LAYOUT_*` 开关的 `legacy` 分支 + `_TRANSITION_*` 镜像写 | 开关已全部翻到 v1:删 legacy 分支,开关常量保留但收窄为断言(值非 v1 → 启动报错),下个大版本再删常量本身。 |
| `character_growth` 只读 legacy 面 | grep 读者:唯一读者是 `get_growth` 工具(memory 类,主链路未接)→ 若确认再无其他读者,工具与模块一起删,`_TOOL_REGISTRY` 同步;有读者 → 列清单不动,PR 里说明。 |
| `_p("diary_context")` 等旧路径分支 | 同引用计数流程。 |

每删一项,对应 docs(memory.md / tools.md / AGENTS.md 速查表)同步删条目——
文档同步 hook 会拦,别绕。

## 3. 静默失败可见化(审计 §2.3 的分级落地)

**不改任何一处现有 except。** 新增:

- `core/silent_failure.py`:`note(module: str, err: Exception)`,进程内计数
  {module → (count, last_error_str, last_ts)},零依赖、自身绝不抛错。
- 只挂**记忆写入路径**的既有 fail-open 点(拍板范围,不扩):`turn_sink` 落库失败、
  `fixation_pipeline` 各 handler 兜底、`short_term.save` / `event_log.append` /
  `episodic` / `mid_term` 的 except 分支,以及 Brief 34 §4 留的 TODO 点。
  每处一行 `silent_failure.note(...)`,原 log 行为不变。
- `GET /system/health`(挂 `admin/routers/system.py`,scope 对齐同文件现有路由):
  返回计数表 + 进程启动时间。不做 UI、不做告警推送——先让数据存在。

## 4. 顺带收尾(审计 §3.3,裁定:只清用户可见面)

- 日志与用户可见文案:简繁统一为简体(`main.py:834` 那类);日志行里的
  `N7-B`/`Brief 28` 等工单号改为语义短语(如 `path_c_tool_loop`)。
- **代码注释里的工单号一律保留**(裁定书:化石也是地图)。
- 本项体力活,cc 可分批,不阻塞 1–3。

## 5. 惯例入册

`AGENTS.md` 新增一节"工作惯例":**每积累若干个功能 brief,安排一个删除 brief;
删除 brief 中测试随功能一起删除是合法且必须的**。(采纳审计 §2.1/§五 的精神,
让"敢做减法"从个人判断变成流程。)

## 6. 测试

1. `intent_reflex.enabled=false`(默认)→ _parse_and_execute_intent 零执行;true → 原行为回归(现有 Path B 测试全量保留并在 true 下通过)。
2. 化石删除:每项删除后全量 pytest 通过;DLQ 检查逻辑本身有测试(空/非空两支)。
3. silent_failure:note 自身抛错不外泄;计数正确;/system/health 返回结构;挂点触发(mock 一个写失败)后计数 +1。

## 7. 不做什么

- 不删 Path B 代码本体(等观察期);不动 627 处 except 的其余部分;
- 不做告警/通知(健康端点先存在,消费方式以后再说);
- 不碰 `_sanitize_assistant_message`、函数级 import、两套串行机制(裁定书均已驳回或降级)。

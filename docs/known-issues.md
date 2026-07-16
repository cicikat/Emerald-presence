# docs/known-issues.md — 已知问题与技术债

> 最近核对：2026-07-16（cc-tasks/28 三仓技术债清盘）。
> 这里只保留仍需行动或观察的条目；已关闭条目的完整背景保留在 Git 历史。

## 当前仍存在

### PB4：Path B 降级观察期

**状态**：`observe`
**到期倒计时**：2026-08-10 到期。到期无缺口记录就开删除 brief。

`config.intent_reflex.enabled` 默认关闭，旧 Path B 守卫暂留。观察期若出现 tool loop 已启用但“角色说了要做却没做”的用户可感缺口，在此登记触发消息、期望动作和实际结果；到期仍无记录则整删 `_parse_and_execute_intent`、守卫、幂等窗口及对应测试。

### H1：hidden_state 现实侧写入链未接线

**状态**：`open`（等待 RealityEventType 映射拍板）
**位置**：`core/memory/user_hidden_state_integrator.py`、`core/pipeline.py::post_process`

读写 primitives、存储和观测面已具备，现实对话仍没有调用 `integrate_event_and_save` / `integrate_impression_and_save`。下一步是按 `cc-tasks/08b-hidden-state-接现实写入.md` 拍板现实信号到 `RealityEventType` 的映射，再在 `uid_lock` 内以 `stamp_user_chat()` 接线并补场景测试。未拍板前不猜测业务含义。

### ACT-1：阅读动向跨角色串桶

**状态**：`observe`（前端已分桶，待复现观察）
**位置**：后端 activity 路径；前端 `SubFlow.tsx`

后端已确认按 `char_id + uid` 隔离且无角色默认参数。PresenceKit-desktop 已于 2026-07-16 将时间轴改为 `subflow_timeline:{charId}`，旧全局桶一次性迁入当时激活角色并删除。若仍复现，再核对操作时的 `active_character` 与后端请求。

### ACT-2：反坍缩重试未覆盖流式路径

**状态**：`open`（需独立设计）
**位置**：`core/pipeline.py::Pipeline.run_llm_stream()`

非流式路径可在发现重复句首后丢弃并重试；流式 token 已对用户可见，不能直接套用。下一步需在“暂缓前 N token”与“流式只接受软降级”之间完成设计、延迟评估和协议验收。

### P3：裁剪后 `layers_activated` 仍包含已删除层

**状态**：`open`
**位置**：`core/prompt_builder.py` token 强制裁剪

下一步：从最终 messages 重算 effective layers，另保留 `layers_before_trim`，并补裁剪回归测试。

### F8：管理面板对话 UI 右键历史未实现

**状态**：`post-v0.1`
**位置**：`admin/static/index.html`

不影响主链路。需要时另开管理面体验工单，不在后端技术债清盘中扩张范围。

### DREAM-1：身份稳定性测试仍是弱代理

**状态**：`observe`

人称与依恋关键词只提供最低限度信号；`GET /dream/invariants` 已补跨梦矛盾观测。继续以实际游玩和 identity eval 双轨观察。

### identity-2：identity 注入有冷启动期

**状态**：`observe`

新用户需经过 mid-term → episodic → consolidate 才开始注入。先观察首个有效维度需要的轮数，再决定是否调阈值。

### TD-1：`sandbox.py` 兼容层

**状态**：`observe`

`core/data_paths.py` 已承接实现，但大量调用与测试 fixture 仍依赖 `core.sandbox.get_paths()`。当前把它当稳定兼容层，不为命名整洁做大范围替换。

### Brief 28/29 运行观察

**状态**：`observe`

- tool loop 与 QQ 关键词快速路径理论上可能在同轮重复执行幂等工具；出现有副作用的快速路径前重新评估。
- MCP 工具描述和结果是不可信输入；v1 只有截断和来源边界，后续需要时按 web 召回同级做内容隔离。

## design-backlog

以下条目都等待设计拍板，不再伪装成“等人写代码”。启动任一项时从 Git 历史取回原详情并单独开工单。

- D7：角色日记是否反向进入长期认知。
- G4：花园 `dry` / `gift` / `ask` 的采后最终容器。
- DESIGN-1：感知数据何时可直接说、何时只影响态度。
- DESIGN-2：主动联系与不打扰的边界。
- SC1：酒馆卡导入卫生、输出风格冲突与 token 预算；模块继续冻结。
- REC1：召回准入从硬名单升级为长度、信息量、新颖度启发式。
- P2-1：用户明确要求“再读一遍”时是否允许绕过工具已读指纹。
- PB1：用户日记、角色记录与情景记忆的来源隔离；等待当前召回链复评。

## 用户动作（代码侧无事可做）

- SEC-AUTH-2 P4 后半：各持有方切换新 token；ESP32 重烧录；Watch Shortcut 与管理面板换值；全部确认后再轮换 legacy secret。
- `data/runtime/auth/audit.jsonl` 约 200 条 `ip=testclient` 测试噪音：由用户决定是否手动清空，本工单不删除数据。

## 本轮已核对关闭

| 编号 | 结论 |
|---|---|
| ADMIN-1 | `jailbreak_entries.py` 已导入 `pathlib.Path`。 |
| F11 | Brief 28/29 tool loop 默认 categories 已包含 `memory`，生成侧接线完成。 |
| P2 `_layer` | `llm_client.py` 在 provider 边界统一调用 `sanitize_messages()`。 |
| PB3 | episodic 加载 fail-loud；空列表覆写非空文件护栏、写后 JSON 校验和 `.bak` 均存在。 |
| TEST-1 | `test_sandbox_paths.py` 已断言 `runtime/channel_queue.json`，旧 `_identity_file` 全仓零命中。 |
| B11 / F10 / D2 / P1 / SEC-AUTH-1 / SEC-WS-1 / identity-1 / TD-2 / TD-3 | 均已完成，已从当前问题区移除。 |
| PB2 | 2026-07-16 在 `1.5_fact_boundary` 加桌宠身份锚点；空屏幕感知时明确禁止虚构屏幕场景，并有专项测试。 |

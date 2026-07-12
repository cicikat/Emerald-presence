# Brief 57 · 花钱动作框架：支出台账 + API 余额监控充值链路（阶段 2）

> 依赖：无（可与 56 并行）。**默认全关**。
> 参考：AP2/MPP 的 mandate 思想（意图单 + 预算封顶 + 审计三件套）；
> "风险 = 自主度 × 访问权"——本单先建框架和最低风险的第一个动作（API 充值），
> 网购类动作是后续工单，必须跑在这套台账之上。
> 原则：**v1 不自动扣款**。agent 只做"检测 → 生成充值请求 → 通知用户"，
> 用户点链接完成支付；自动执行留给 v2（平台有 auto-topup API 且用户拍板后）。

## 1. 支出台账（新文件 core/actions/spend_ledger.py）

所有"花钱类动作"的强制收口，先于任何具体动作存在：

- 存储：`data/runtime/spend/ledger.jsonl`（data_paths 访问器，Hard Rule 1；
  `safe_append_jsonl`；追加只增不删）。
- 行 schema：

```json
{"ts": ..., "action": "api_topup", "payee": "deepseek", "amount": 50.0,
 "currency": "CNY", "status": "proposed|notified|confirmed|rejected|capped",
 "origin": "scheduler|user_live", "mandate_id": "sp_...", "note": "..."}
```

- **额度守卫（fail-closed）**：`check_budget(action, amount)` 读 config
  `spend: {enabled: false, daily_cap: 0, monthly_cap: 0, payee_whitelist: []}`——
  enabled=false / 超日或月上限 / payee 不在白名单 → 拒绝并落 `status=capped` 行 + 通知。
  上限统计按台账当日/当月 `confirmed` 行求和，**不信内存计数**（重启不丢）。
- 台账写失败 → 动作本身**中止**（这是全仓少数 fail-closed 优先于 fail-open 的点：
  记不了账就不许花钱），与 Write Envelope 同哲学。

## 2. 第一个动作：API 余额监控 + 充值请求

1. **余额查询 adapter**（core/actions/api_balance.py）：`config.spend.balance_providers`
   列表（`name / base_url / api_key / threshold`），OpenAI-compat `GET /balance` 或
   provider 专用端点各写一个小函数；查不到的 provider 跳过（fail-open）。
2. **调度器 trigger**（core/scheduler/triggers/spend_monitor.py，仿 hidden_state_decay：
   `stamp_trigger()`，每日一次，不发言）：余额 < threshold →
   台账落 `proposed` 行 → 生成充值链接/指引 → 经现有通知通道推送（ntfy 中继已有）
   → 更新 `notified`。同 provider 冷却 48h（防重复轰炸）。
3. 用户完成支付后无回执可查的 provider：下次 tick 查到余额回升 → 自动落 `confirmed` 行闭环。

## 3. 角色侧接入

- 台账动作经 `action_trace`（Brief 27 现成埋点）回流："他提醒过你 API 快没钱了"
  是角色记得的操作，不是无声后台脚本（Adaptation Paradox 的教训）。
- 通知文案走角色口吻模板（`char_name` 插值，Hard Rule 8），不走裸系统通知。

## 4. 拍板

- v1 边界写死：**不保存任何支付凭据、不自动提交任何支付表单、不碰浏览器**。
  代码里不出现卡号/支付密码字段，schema 层面就没有位置放它们。
- 后续网购工单的准入条件（写进本单 docstring，给未来的自己看）：
  台账平稳运行 ≥1 个月、独立小额卡就位、意向单确认流设计过审。
- `admin/routers/spend.py`：`GET /spend/ledger?limit=`（只读，admin scope）+
  `GET /spend/budget`（当前额度用量）。不做写端点——config 手改。

## 5. 测试

1. enabled=false → trigger 零动作零落账。
2. 余额低于阈值 → proposed + notified 两行、通知发出、48h 冷却内不重发。
3. 日上限：当日 confirmed 求和 + 新 amount 超 cap → capped 行 + 拒绝；月上限同理。
4. payee 不在白名单 → capped。
5. 台账写失败（mock 磁盘异常）→ 动作中止，无通知发出（fail-closed 验证）。
6. 余额回升 → confirmed 闭环行。
7. action_trace 含台账动作条目。
8. `pytest -n auto` 新增测试文件 + scheduler 相关回归。

## 6. 不做什么

- 不做任何自动扣款/表单提交/浏览器自动化（v2 另立项，先过拍板条件）。
- 不接支付协议 SDK（AP2/x402 是美国生态，只借 mandate 思想）。
- 不做网购（独立工单，前置条件见拍板）。
- 不给 LLM 暴露任何 spend 工具（`_TOOL_REGISTRY` 本单不动——充值链路由调度器驱动，
  不是对话内工具；对话内"帮我充值"场景等台账稳定后评估）。

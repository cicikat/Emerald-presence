# Brief 70 · 审查修复：成长/幽灵/Stage 逻辑缺陷（2026-07-12 复审产出）

> 来源：Fable 对 50–53 / 56–61 落地代码的只读复审。按危害排序，全部小修，一单打包。
> 另：**Brief 54（投影参与度加权）与 55（char_relations）实际未实现**——cc-tasks 文件
> 在库但代码未动，按原工单重跑，不在本单范围。

## 1. 🔴 spend_monitor confirmed 幽灵行（core/scheduler/triggers/spend_monitor.py）

现状：余额恢复分支只查"存在 notified 行"就追加 confirmed，每日 tick 重复追加；
confirmed 计入 `budget_usage` → 幽灵支出吃满日/月额度 → 后续真实动作被误 capped。

修法：按 `mandate_id` 配对——只对"该 payee 存在 notified 行、且其 mandate_id 无对应
confirmed 行"的 mandate 补**一次** confirmed（沿用 notified 行的 mandate_id 与 amount）。
测试：恢复后连跑 3 个 tick 只产生 1 条 confirmed；budget_usage 不再随 tick 增长。

## 2. 🔴 新兴趣饥饿（core/scheduler/triggers/practice.py::select_interest）

现状：权重 `max(0, learning_progress)`，无分数的新兴趣权重 0，只要任一老兴趣 >0
就永远选不中 → 永远没有第一次练习。

修法：`weights = [BASELINE_WEIGHT + max(0.0, progress) for ...]`，`BASELINE_WEIGHT = 0.1`
命名常量。测试：新兴趣（无分数）与 progress=0.5 的老兴趣并存时，10000 次抽样中
新兴趣命中率 ≈ 0.1/0.7（统计断言，容差放宽）。

## 3. 🟡 notes replaces 死路（core/growth/notes.py::apply_note）

现状：相似度去重先于 replaces 处理；改写版必然与被改写条相似 → replaces 永不生效。

修法：`replaces` 合法时先执行替换，相似检查改为只对**其余**条目做（排除
`entries[replaces-1]`）；replaces 非法/缺省时维持现有全量去重。
测试：对第 3 条做近似改写 + replaces=3 → 成功覆盖；replaces=null 且相似 → 仍拒绝。

## 4. 🟡 Phase B echo 误比 owner（core/stage/runner.py）

现状：`previous_ai_content=transcript[-1].content` 未检查说话人；Phase A 零回复时
上一条是 owner，回应/呼应用户的话被误掐（工单明确豁免回应 owner 的相似）。

修法：`previous_ai_content=transcript[-1].content if transcript[-1].speaker_id != "owner" else None`。
测试：Phase A 零回复进入 Phase B，AI 回复与 owner 消息高相似 → 不掐；与上一条 AI 高相似 → 掐。

## 5. 🟡 练习条目进不了日记（core/growth/practice_session.py）

现状：`action_trace.record(..., echo_event_log=False)` → 不进 event_log →
23:00 日记生成看不到练习，"日记自然消化"断链（层 10.5 可见不受影响）。

修法：改 `echo_event_log=True`（回流的只有"练了X，一句感受"的事实行，无作品全文，
不违反隔离红线）。`_record_unlock` 的 trace 保持与之一致。
测试：session 后 event_log 含练习行且不含作品正文（负向断言保留）。

## 6. 🟡 interest_seed 话题候选质量（core/scheduler/triggers/interest_seed.py）

现状：`Counter(w for ... if w in text)` 是 presence 计数（恒 1），无频率排序；
候选名为单字（"写"/"歌"），兴趣名不像人话；未按工单用 tag_rules。

修法（最小改）：改为 `sum(text.count(w) for w in words)` 按 **domain** 聚合频次，
domain 频次 top 2 生成候选，name 用 domain 的中文短语表（"写点东西"/"玩玩音乐"/
"学着画画"，常量表，LLM 遴选时可改名——add_interest 用 LLM pick 的名字）。
注意：choose_candidate 校验 pick 必须在候选 name 集内的逻辑同步放宽为
"pick 在候选内 或 rationale 合理时允许 LLM 对候选改名"→ **不放宽**，保持白名单校验，
改名交给候选表本身（最小面）。
测试：文本含 5 次"画"1 次"歌" → drawing 候选排前；候选名非单字。

## 7. 🟢 低优先级三件（同单顺手修）

- **perception 首帧冷却误判**：`_last_accepted` 缺省 0 + `time.monotonic()` 启动后
  5 分钟内首帧被判 cooldown。修：`_last_accepted.get(source)` 为 None 时视为无冷却。
- **cleanup_visual_trace 无人调用**：核实后挂入现有日度清理调度（若确无挂接）；
  有挂接则本条关闭。
- **config.example.yaml 注释补两条**：mcp_proficiency tiers 每档必须写全量工具列表
  （高档不含低档条目会导致断档）；spend daily_cap/monthly_cap 的 0 = 全禁（fail-closed 语义）。

## 8. 观察项（不修，记录）

- echo 相似度 min 归一化对短回复偏激进：跑两周看 arbiter_trace 的 echo_cut 率再调阈值。
- trace `addressed` 字段含 mention：观测语义略宽，可接受。
- `_keyword_relevance` 已成死代码：下一个删除 brief 一并清。
- spend 通知仅走 mobile 通道：channel 缺失时 proposed 行日增（无资金危害）；
  若用户确认 ntfy 为主通道则改走 ntfy，本单不拍。

## 9. 验收

`pytest -n auto` 相关测试文件 + 新增用例全绿；memeval 与 stage 测试无回归。
每个编号独立 commit（1/2 优先）。

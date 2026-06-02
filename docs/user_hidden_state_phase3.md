# User Hidden State — Phase 3 设计规划

> 前置：Phase 0–2 已完成（schema / primitive / persistence / Dream read）。
> Phase 3 目标：激活所有长期层写入路径，接入调度器，完成 Dream snapshot 正式注入，补全假绿边界。
> **限制**：不新增 schema 字段，不改 Phase 2 MVP 已实现逻辑，所有长期层写入必须 WriteEnvelope gated。

---

## 1. Integrator 类型保护方案

### 当前问题

`integrate_event` 在创建 `IntegratorResult` 时首先访问 `event_type.value`。传入错误类型（如 `DreamBodyStateEvent`）会抛出 `AttributeError`，是 fail-closed 行为但错误类型不明确（EC-38 文档了此现象）。

### Phase 3 保护规则

**A. `integrate_event` 入口守卫**

```python
# 函数体第一行（在 result 构造之前）
if not isinstance(event_type, RealityEventType):
    raise TypeError(
        f"integrate_event: event_type must be RealityEventType, got {type(event_type).__name__}"
    )
```

- 错误类型 → `TypeError`（明确，不是 AttributeError）
- 不改变已有 fail-closed 语义：异常在任何状态变更前抛出

**B. `integrate_impression` 入口守卫**

```python
if not isinstance(impression, ImpressionInput):
    raise TypeError(
        f"integrate_impression: impression must be ImpressionInput, got {type(impression).__name__}"
    )
```

**C. `_and_save` uid 守卫**（两个 disk-wired 入口共用）

```python
if not isinstance(uid, (str, int)):
    raise TypeError(f"uid must be str or int, got {type(uid).__name__}")
```

**D. 长期层运行时守卫函数**（新增，在 integrator 模块顶部）

```python
_LONG_TERM_FIELDS: frozenset[str] = frozenset({
    "sensitivity.baseline",
    "touch_need.baseline",
    "embodied_ease",
    "body_memory",
})

def _assert_not_long_term(field_name: str) -> None:
    """内部断言：任何 integrate_* 函数都不得触及长期层。"""
    if field_name in _LONG_TERM_FIELDS:
        raise RuntimeError(
            f"integrator attempted to write long-term field '{field_name}' — "
            "must go through consolidation/decay scheduler path only"
        )
```

> 此函数在 integrate_event / integrate_impression 的 FieldDelta 构造前调用，确保中期层函数无法意外写长期层。Phase 3 新增的长期层写入路径（apply_time_decay、consolidate_baselines、reinforce_body_memory 等）**不经过 integrator**，直接由调度器持有的 envelope 调用。

**E. WriteEnvelope 类型守卫（user_hidden_state.py 内）**

所有接受 `source: UpdateSource` 参数的函数（`nudge_current_sensitivity`、`nudge_embodied_ease`、`reinforce_body_memory`、`discharge_touch_deficit`）在函数体内验证：

```python
if not isinstance(source, UpdateSource):
    raise TypeError(f"source must be UpdateSource, got {type(source).__name__}")
```

---

## 2. Scheduler / apply_time_decay 调度方案

### 2-A. `apply_time_decay` 实现规则

在 `core/memory/user_hidden_state.py` 中移除 `NotImplementedError`，实现如下：

**输入**：`state: UserHiddenState`, `now: str`（ISO-8601 UTC）
**前提**：调用方已持有 `WriteEnvelope.can_write_memory=True`

**elapsed_days 计算**：

```
若 state.last_decay_tick is None:
    elapsed_days = 0.0   ← 首次运行，不应用任何衰减（safe first-run）
否则:
    elapsed_days = (parse(now) - parse(last_decay_tick)).total_seconds() / 86400
    若 elapsed_days < 0:
        elapsed_days = 0.0   ← 时钟回拨保护
```

**衰减规则**（全部用 `_regress(current, target, elapsed_days, half_life_days)`）：

| 字段 | 目标值 | 半衰期常量 |
|---|---|---|
| `sensitivity.current.value` | `sensitivity.baseline.value` | `CURRENT_SENS_REGRESS_HL_DAYS = 5` |
| `sensitivity.baseline.value` | `SCALAR_CENTER (50.0)` | `SENS_BASELINE_CENTER_HL_DAYS = 180` |
| `touch_need.deficit.value` | `0.0` | `TOUCH_DEFICIT_DECAY_HL_DAYS = 10` |
| `touch_need.baseline.value` | `SCALAR_CENTER (50.0)` | `TOUCH_BASELINE_CENTER_HL_DAYS = 180` |
| `embodied_ease.value` | `SCALAR_CENTER (50.0)` | `EMBODIED_EASE_CENTER_HL_DAYS = 90` |
| 每条 `body_memory.entries[i].weight` | `0.0` | `MEMORY_EXTINCTION_HL_DAYS = 45` |

**写入顺序**（注：body_memory 条目 weight 衰减但不自动蒸发——蒸发仅在 `reinforce_body_memory` 内触发）：

```python
# sensitivity 衰减（中期 current → baseline；长期 baseline → center）
new_sens_current = _clamp(_regress(
    state.sensitivity.current.value,
    state.sensitivity.baseline.value,
    elapsed_days, CURRENT_SENS_REGRESS_HL_DAYS,
))
state.sensitivity.current.value = new_sens_current
state.sensitivity.current.last_updated = now
state.sensitivity.current.last_update_source = UpdateSource.TIME_DECAY

new_sens_baseline = _clamp(_regress(
    state.sensitivity.baseline.value,
    SCALAR_CENTER, elapsed_days, SENS_BASELINE_CENTER_HL_DAYS,
))
state.sensitivity.baseline.value = new_sens_baseline
state.sensitivity.baseline.last_updated = now
state.sensitivity.baseline.last_update_source = UpdateSource.TIME_DECAY

# touch_need 衰减
new_deficit = _clamp(_regress(
    state.touch_need.deficit.value,
    0.0, elapsed_days, TOUCH_DEFICIT_DECAY_HL_DAYS,
))
state.touch_need.deficit.value = new_deficit
state.touch_need.deficit.last_updated = now
state.touch_need.deficit.last_update_source = UpdateSource.TIME_DECAY

new_tn_baseline = _clamp(_regress(
    state.touch_need.baseline.value,
    SCALAR_CENTER, elapsed_days, TOUCH_BASELINE_CENTER_HL_DAYS,
))
state.touch_need.baseline.value = new_tn_baseline
state.touch_need.baseline.last_updated = now
state.touch_need.baseline.last_update_source = UpdateSource.TIME_DECAY

# embodied_ease 衰减
new_ease = _clamp(_regress(
    state.embodied_ease.value,
    SCALAR_CENTER, elapsed_days, EMBODIED_EASE_CENTER_HL_DAYS,
))
state.embodied_ease.value = new_ease
state.embodied_ease.last_updated = now
state.embodied_ease.last_update_source = UpdateSource.TIME_DECAY

# body_memory weights 衰减（不蒸发，不排序）
for entry in state.body_memory.entries:
    new_w = _clamp(
        _regress(entry.weight, 0.0, elapsed_days, MEMORY_EXTINCTION_HL_DAYS),
        lo=WEIGHT_MIN, hi=WEIGHT_MAX,
    )
    entry.weight = new_w

# 更新 tick
state.last_decay_tick = now
return state
```

### 2-B. `accrue_touch_deficit` 实现规则

移除 `NotImplementedError`：

```python
accrual_per_day = SCALAR_MAX / TOUCH_DEFICIT_DECAY_HL_DAYS  # ~10 points/day
delta = _clamp(accrual_per_day * elapsed_days, lo=0.0, hi=SCALAR_MAX)
state.touch_need.deficit.value = _clamp(state.touch_need.deficit.value + delta)
state.touch_need.deficit.last_updated = now
state.touch_need.deficit.last_update_source = UpdateSource.REALITY_BEHAVIOR
return state
```

> `elapsed_days = 0.0` → delta = 0.0 → no-op（安全）。

### 2-C. 调度器 Trigger

**新文件**：`core/scheduler/triggers/hidden_state_decay.py`

```
触发器名称: hidden_state_decay
冷却时间:   12 * 3600 秒（12小时）
用途:       每12小时对 uid 的 hidden_state 运行一次 apply_time_decay + 原子保存
发言:       不发言（纯后台 tick，不入 pipeline）
Envelope:  stamp_trigger()（can_write_memory=True，已有定义）
```

实现模式（参照 garden_daily 但无 pipeline_send）：

```python
async def _check_hidden_state_decay() -> None:
    if not _is_ready("hidden_state_decay"):
        return
    _mark("hidden_state_decay")

    uid = safe_user_id()
    now = datetime.utcnow().isoformat() + "Z"
    envelope = stamp_trigger()

    state = load_hidden_state(uid)
    state = apply_time_decay(state, now)

    if not save_hidden_state(uid, state):
        logger.error("[hidden_state_decay] save failed for uid=%s", uid)
```

在 `core/scheduler/loop.py` 的 `_COOLDOWNS` 中追加：

```python
"hidden_state_decay":    12 * 3600,   # 用户隐性状态衰减：12小时
"hidden_state_consolidate": 7 * 24 * 3600,  # 基线收敛：7天
```

### 2-D. `consolidate_baselines` 实现规则

移除 `NotImplementedError`，周期触发（7天），**不应用半衰期回归**，而是轻推一步：

```python
def consolidate_baselines(state: UserHiddenState, now: str) -> UserHiddenState:
    # sensitivity.baseline 向 SCALAR_CENTER 拉 BASELINE_LEARN_RATE 分率
    sens_b = state.sensitivity.baseline
    sens_b.value = _clamp(
        sens_b.value + BASELINE_LEARN_RATE * (SCALAR_CENTER - sens_b.value)
    )
    sens_b.last_updated = now
    sens_b.last_update_source = UpdateSource.CONSOLIDATION

    # touch_need.baseline 向 SCALAR_CENTER 拉 BASELINE_LEARN_RATE 分率
    tn_b = state.touch_need.baseline
    tn_b.value = _clamp(
        tn_b.value + BASELINE_LEARN_RATE * (SCALAR_CENTER - tn_b.value)
    )
    tn_b.last_updated = now
    tn_b.last_update_source = UpdateSource.CONSOLIDATION

    return state
```

> `BASELINE_LEARN_RATE = 0.02`（已有常量，每次将 baseline 向 50 推进 2%）。
> 中期层（sensitivity.current, touch_need.deficit, embodied_ease, body_memory）不被 consolidate 触碰。

**调度器 Trigger**：`hidden_state_consolidate`，7天冷却，同样使用 `stamp_trigger()`，不发言。

---

## 3. body_memory reinforce 完整规则

### 3-A. `reinforce_body_memory` 实现

移除 `NotImplementedError`，完整实现：

```
函数签名：
reinforce_body_memory(
    state: UserHiddenState,
    cue: str,
    response_tag: str,
    strength: float,          ← [WEIGHT_MIN, WEIGHT_MAX]，即 [0.0, 1.0]
    source: UpdateSource,
    now: str,
) -> UserHiddenState
```

**步骤**：

1. **Cue 归一化**
   ```python
   cue_norm = cue.strip().lower()
   if not cue_norm:
       return state   # 空 cue → no-op，不报错
   ```

2. **strength 裁剪**
   ```python
   strength = _clamp(strength, lo=WEIGHT_MIN, hi=WEIGHT_MAX)
   ```

3. **查找已有 entry**（大小写不敏感，以 `cue.strip().lower()` 为 key）
   ```python
   existing = next(
       (e for e in state.body_memory.entries if e.cue.strip().lower() == cue_norm),
       None,
   )
   ```

4. **Hebbian 强化（若已存在）**
   ```python
   if existing is not None:
       old_w = existing.weight
       # 渐近强化：每次推近 1.0，但永远不超过 WEIGHT_MAX
       existing.weight = _clamp(old_w + strength * (WEIGHT_MAX - old_w), lo=WEIGHT_MIN, hi=WEIGHT_MAX)
       existing.last_reinforced = now
       existing.response_tag = response_tag   # 最新 response_tag 覆盖旧值
       return state
   ```

5. **新 entry 路径**
   ```python
   new_entry = BodyMemoryEntry(
       cue=cue_norm,
       response_tag=response_tag,
       weight=_clamp(strength, lo=WEIGHT_MIN, hi=WEIGHT_MAX),
       created_at=now,
       last_reinforced=now,
   )

   if len(state.body_memory.entries) < state.body_memory.max_entries:
       state.body_memory.entries.append(new_entry)
       return state

   # 满容量：找 weight < MEMORY_EVICT_EPS 的最低权重条目蒸发
   evict_candidates = [e for e in state.body_memory.entries if e.weight < MEMORY_EVICT_EPS]
   if not evict_candidates:
       # 无可蒸发条目：静默丢弃新 entry（不报错，记录 debug log）
       logger.debug(
           "[body_memory] capacity full, no evictable entry — new cue '%s' dropped", cue_norm
       )
       return state

   # 蒸发最低权重者
   weakest = min(evict_candidates, key=lambda e: e.weight)
   state.body_memory.entries.remove(weakest)
   state.body_memory.entries.append(new_entry)
   return state
   ```

**调用限制**：
- 只有 `source=UpdateSource.REALITY_BEHAVIOR` 在 Phase 3 接入（Reality turn 直接观测体感 cue）
- `UpdateSource.DREAM_BODY_EVENT` 接口保留但 Phase 3 不经调度器——保留至 Dream 接入阶段
- `UpdateSource.SENSOR_SIGNAL` 永远不得调用此函数，除非调用方 WriteEnvelope 显式包含 sensor 授权

### 3-B. `nudge_embodied_ease` 实现

移除 `NotImplementedError`：

```python
def nudge_embodied_ease(
    state: UserHiddenState,
    delta: float,
    source: UpdateSource,
    now: str,
) -> UserHiddenState:
    if not isinstance(source, UpdateSource):
        raise TypeError(...)
    # delta 上限：单次不得超过 MAX_NUDGE_PER_EVENT
    delta = _clamp(delta, lo=-MAX_NUDGE_PER_EVENT, hi=MAX_NUDGE_PER_EVENT)
    state.embodied_ease.value = _clamp(state.embodied_ease.value + delta)
    state.embodied_ease.last_updated = now
    state.embodied_ease.last_update_source = source
    return state
```

> `embodied_ease` 是长期体质字段，Phase 3 不经 integrate_event / integrate_impression 写入——由调度器或专用整合 pass 持 `stamp_trigger()` 调用。

### 3-C. Integrator 新增 body_memory 事件接口（Phase 3）

在 `user_hidden_state_integrator.py` 追加新入口：

```python
def integrate_body_cue(
    cue: str,
    response_tag: str,
    strength: float,
    hidden_state: UserHiddenState,
    write_envelope: WriteEnvelope,
    now: str,
) -> tuple[UserHiddenState, IntegratorResult]:
    """将一个 body cue 强化写入 body_memory（长期层）。

    规则：
      - write_envelope.can_write_memory 必须为 True。
      - source 固定为 REALITY_BEHAVIOR（Phase 3）。
      - cue 为空或全空白 → 静默不写（返回 accepted=False，无 rejected_reasons）。
      - 调用 reinforce_body_memory，由其负责容量管理和 Hebbian 权重更新。
    """
```

并配套：

```python
def integrate_body_cue_and_save(
    uid: str | int,
    cue: str,
    response_tag: str,
    strength: float,
    write_envelope: WriteEnvelope,
    now: str,
) -> tuple[UserHiddenState, IntegratorResult]:
    """load → integrate_body_cue → save（仅 accepted + can_write_memory 时写盘）。"""
```

> body_memory 是长期层，integrator 的 `_LONG_TERM_FIELDS` 守卫不拦截 `integrate_body_cue`，因为 `integrate_body_cue` 的职责就是写 body_memory——由 Phase 3 显式开放此路径。需要更新 `_LONG_TERM_FIELDS` 注释，注明 body_memory 的合法写路径是 `integrate_body_cue*`。

---

## 4. Dream snapshot 使用说明 + fail-closed 边界

### 4-A. 正式注入点

**fetch_context() 增加调用**（`core/pipeline.py` 步骤1）：

```python
# 与 user_identity.format_for_prompt() 并发拉取
hidden_state_snapshot = load_dream_snapshot(uid, now_str)
```

**build_prompt() 新增 layer**（`core/prompt_builder.py`）：

```python
{
    "_layer": "user_hidden_state_snapshot",
    "role": "system",
    "content": _format_hidden_state_snapshot(hidden_state_snapshot),
}
```

Layer 位置：插在 `6a_user_identity` 之后（可与 mid_term 层同组），tag gating 条件为 `body_intimate` 或 `physical_closeness` 标签激活（不是每轮都注入）。

**`_format_hidden_state_snapshot`**（不暴露原始 float，只输出 bucket label）：

```
[用户当前身体感知参考]
敏感度：{sensitivity}        ← low / mid / high
触碰需求：{touch_appetite}   ← low / mid / high
身体接触舒适度：{embodied_ease}  ← guarded / neutral / easy
条件化身体记忆线索：{memory_cues}  ← ["cue_a", "cue_b", ...]（最多5条，权重不暴露）
```

### 4-B. Pruning 资格

`user_hidden_state_snapshot` layer 加入 token 裁剪表（低优先级，先于 mid_term 被裁）：

```
裁剪顺序更新：
6b_event_search → user_hidden_state_snapshot → mid_term → 6d_diary → 6e_inner_diary → 6c_episodic → 5.5_lore
```

### 4-C. Fail-closed 边界清单

| 边界 | 机制 | 行为 |
|---|---|---|
| load 失败（文件不存在/损坏） | `load_hidden_state` 返回 `default_hidden_state()` | 中性快照（all mid/neutral） |
| `to_dream_snapshot` 内异常 | `try/except Exception` → `_NEUTRAL` | 中性快照，不抛出 |
| Dream session 内调用写路径 | `DREAM_DIRECT_WRITABLE = frozenset()` 文档约束 + integrator 无 Dream 入口 | 没有任何写路径可达 |
| Dream 读到快照后试图写回 | 没有写回接口（`load_dream_snapshot` 纯读） | 物理不可能 |
| snapshot 包含原始 float | `to_dream_snapshot` 仅输出 bucket string | float 从不出现在返回值中 |
| 调度器 tick 无 envelope | 调度器固定使用 `stamp_trigger()`；`save_hidden_state` 调用方负责 | 调用方不传 envelope 则 apply_time_decay 返回值不得被保存 |

### 4-D. Dream pipeline 隔离不变量（Phase 3 期间）

Phase 3 的 Dream snapshot 注入仅用于 **Reality 对话** 的 prompt 构建，不进入 Dream pipeline。Dream pipeline 独立于现实 pipeline，见 `docs/dream.md`。Dream session 结束后的 integrator 调用（`integrate_impression_and_save`）是 Phase 2 已实现的 Reality-side 接口，Phase 3 不改变这条路径。

---

## 5. 测试覆盖矩阵设计

新文件：`tests/test_user_hidden_state_phase3.py`

总计 **34 个测试**，按功能组划分：

### Group A — `apply_time_decay`（9 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| AT-01 | `last_decay_tick=None` → elapsed=0 → 所有字段不变，last_decay_tick 更新 | first-run 安全 |
| AT-02 | elapsed=0.0（刚 tick）→ 字段值不变 | 零时间 no-op |
| AT-03 | elapsed=5d → sensitivity.current 向 baseline 移动约 50%（5d = 1× HL） | 半衰期精度 |
| AT-04 | elapsed=10d → touch_need.deficit 约减半 | 半衰期精度 |
| AT-05 | elapsed=90d → embodied_ease 向 SCALAR_CENTER 移动约 50%（90d = 1× HL） | 半衰期精度 |
| AT-06 | body_memory 单 entry weight 衰减（45d ≈ 半衰）→ weight ≈ 原始 × 0.5 | 长期层衰减 |
| AT-07 | 衰减后 `last_decay_tick` 更新为 `now` | tick 更新 |
| AT-08 | `last_decay_tick` 在 `now` 之后（时钟回拨）→ elapsed=0 → 不衰减 | 时钟保护 |
| AT-09 | 衰减不蒸发 body_memory 条目（weight 降低但条目数不变） | 蒸发边界 |

### Group B — `consolidate_baselines`（5 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| CB-01 | sensitivity.baseline 偏高 → 轻推向 SCALAR_CENTER（Δ = BASELINE_LEARN_RATE × 距离） | 推进量精度 |
| CB-02 | touch_need.baseline 偏低 → 轻推向 SCALAR_CENTER | 推进量精度 |
| CB-03 | 两 baseline 均在 SCALAR_CENTER → 调用后不变 | 已收敛 no-op |
| CB-04 | consolidate 不触碰 sensitivity.current / deficit / embodied_ease / body_memory | 中期层隔离 |
| CB-05 | 调用后 last_update_source == CONSOLIDATION | source 审计 |

### Group C — `reinforce_body_memory`（10 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| RM-01 | 空 memory + 新 cue → 添加 entry，weight = strength | 基本写入 |
| RM-02 | 已有 cue → Hebbian 强化：new_weight = old + strength × (1 - old) | Hebbian 精度 |
| RM-03 | 已有 cue → last_reinforced 更新为 now | 时间戳 |
| RM-04 | 已有 cue → response_tag 更新为新值 | 字段覆盖 |
| RM-05 | 空 cue（""）→ no-op，entry 数不变 | 空输入保护 |
| RM-06 | 全空白 cue（"   "）→ no-op | 空白归一化 |
| RM-07 | 满容量 + 有低权重 entry（weight < MEMORY_EVICT_EPS）→ 最弱者被蒸发，新 cue 加入 | 蒸发路径 |
| RM-08 | 满容量 + 无低权重 entry → 新 cue 静默丢弃，entry 数不变 | 满容量保护 |
| RM-09 | 重复强化 weight → 永远不超过 WEIGHT_MAX | 权重上限 |
| RM-10 | strength=0.0 新 cue → weight=0.0，entry 添加（零权重合法） | 边界 |

### Group D — `nudge_embodied_ease`（4 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| EE-01 | 正常 delta → embodied_ease 正确更新 | 基本更新 |
| EE-02 | delta > MAX_NUDGE_PER_EVENT → 裁剪至 MAX_NUDGE_PER_EVENT | 单次上限 |
| EE-03 | 大正 delta → 不超过 SCALAR_MAX | 上界 clamp |
| EE-04 | 大负 delta → 不低于 SCALAR_MIN | 下界 clamp |

### Group E — `accrue_touch_deficit`（3 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| TD-01 | elapsed_days=1.0 → deficit 增加约 10 points（10 = SCALAR_MAX / TOUCH_DEFICIT_DECAY_HL_DAYS） | 基本累积 |
| TD-02 | elapsed_days=0.0 → no-op | 零时间 |
| TD-03 | 从 SCALAR_MAX 开始 → 不超过 SCALAR_MAX | 上界 |

### Group F — `integrate_body_cue` + disk-wired（4 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| BC-01 | open envelope + 有效 cue → body_memory 写入，accepted=True | 基本路径 |
| BC-02 | closed envelope → rejected，disk 不变 | fail-closed |
| BC-03 | `integrate_body_cue_and_save` round-trip → 磁盘 entry 可 reload 到 | 持久化 |
| BC-04 | body_cue 不触碰 sensitivity.current / deficit | 字段隔离 |

### Group G — 调度器 / apply_time_decay 假绿测试（4 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| SC-01 | stamp_trigger() 有 can_write_memory=True → apply_time_decay + save 路径合法 | 合法入口确认 |
| SC-02 | stamp_debug() → save 调用方应 fail-closed（模拟调度器 bug：错误 envelope） | 假绿保护 |
| SC-03 | apply_time_decay 后 last_decay_tick 比 now 早（正向时间流）→ 下次 elapsed_days > 0 | 时间流正确性 |
| SC-04 | 多次 apply_time_decay 中 body_memory 条目数不变（衰减≠蒸发） | 蒸发边界 |

### Group H — 类型守卫（假绿 TypeError）（5 个）

| 编号 | 名称 | 验证点 |
|---|---|---|
| TG-01 | `integrate_event` 传入 DreamBodyStateEvent → `TypeError`（不是 AttributeError） | 类型保护 |
| TG-02 | `integrate_impression` 传入 str → `TypeError` | 类型保护 |
| TG-03 | `integrate_event_and_save` 传入 uid=None → `TypeError` | uid 保护 |
| TG-04 | `nudge_embodied_ease` source=None → `TypeError` | source 保护 |
| TG-05 | `reinforce_body_memory` source="raw_string" → `TypeError` | source 保护 |

---

## 6. Phase 3 验收标准

以下所有条件必须同时满足才算 Phase 3 完成：

### 功能完整性

- [ ] `apply_time_decay` 不再抛 `NotImplementedError`；所有 AT-* 测试通过
- [ ] `consolidate_baselines` 不再抛 `NotImplementedError`；所有 CB-* 测试通过
- [ ] `reinforce_body_memory` 不再抛 `NotImplementedError`；所有 RM-* 测试通过
- [ ] `nudge_embodied_ease` 不再抛 `NotImplementedError`；所有 EE-* 测试通过
- [ ] `accrue_touch_deficit` 不再抛 `NotImplementedError`；所有 TD-* 测试通过
- [ ] `integrate_body_cue` / `integrate_body_cue_and_save` 新函数实现并通过 BC-* 测试

### 类型安全

- [ ] `integrate_event` 传入错误类型抛 `TypeError`（不是 AttributeError）
- [ ] `integrate_impression` 传入错误类型抛 `TypeError`
- [ ] `_and_save` uid 类型守卫生效
- [ ] 所有 TG-* 测试通过

### 调度器

- [ ] `hidden_state_decay` trigger 在 `loop.py` 注册冷却（12h）
- [ ] `hidden_state_consolidate` trigger 在 `loop.py` 注册冷却（168h）
- [ ] `core/scheduler/triggers/hidden_state_decay.py` 实现 `_check_hidden_state_decay()`
- [ ] 触发器使用 `stamp_trigger()`，不调用 `_pipeline_send()`
- [ ] SC-* 测试通过

### Dream snapshot 注入

- [ ] `fetch_context()` 并发拉取 `load_dream_snapshot`
- [ ] `build_prompt()` 注入 `user_hidden_state_snapshot` layer（tag gated）
- [ ] 新 layer 加入 token 裁剪表，优先级低于 mid_term
- [ ] `_format_hidden_state_snapshot` 不暴露任何 float 原始值
- [ ] `to_dream_snapshot` 已有的 fail-closed 逻辑不变（EC-34 仍通过）

### 安全不变量

- [ ] 所有 Phase 1 / 2 / 2.5 已有测试（EC-01–EC-39）全部不回归
- [ ] 新长期层写入路径（body_memory、embodied_ease、baselines）全部经 WriteEnvelope gated
- [ ] `DREAM_DIRECT_WRITABLE = frozenset()`——新路径不给 Dream 任何写授权
- [ ] 调度器调用 `apply_time_decay` 后 body_memory 条目数不超过 max_entries
- [ ] Dream snapshot 中不出现 float 原始值（仅 bucket string + cue string）

### 文档

- [ ] `ARCHITECTURE.md` Phase 3 条目更新（见下节）
- [ ] 本文档（`docs/user_hidden_state_phase3.md`）作为 Phase 3 的设计 spec 存档
- [ ] `AGENTS.md` 任务映射表更新（若新增了 trigger 文件需列入速查表）

---

## 7. ARCHITECTURE.md 更新说明

替换现有 Phase 2 描述块（ARCHITECTURE.md 第 208–215 行）为：

```
> **Phase 3（长期层激活 + 调度器接入 + Dream snapshot 注入，当前开发中）**：
> `core/memory/user_hidden_state.py` — 所有 stub（apply_time_decay / consolidate_baselines /
>   reinforce_body_memory / nudge_embodied_ease / accrue_touch_deficit）已实现。
> `core/memory/user_hidden_state_integrator.py` — 新增 integrate_body_cue / integrate_body_cue_and_save；
>   类型守卫补全（TypeError on wrong type）。
> `core/scheduler/triggers/hidden_state_decay.py` — 12h decay tick + 168h consolidate tick。
> `core/prompt_builder.py` — user_hidden_state_snapshot layer（tag-gated，body_intimate 触发）。
>
> 长期层写权限分配：
>   body_memory      ← integrate_body_cue（Reality-side，stamp_trigger / stamp_user_chat）
>   embodied_ease    ← nudge_embodied_ease（调度器 / 专用 integrator pass，stamp_trigger）
>   sensitivity.baseline / touch_need.baseline ← apply_time_decay + consolidate_baselines（调度器）
>   所有长期层写入：WriteEnvelope.can_write_memory=True 必须，Dream 不得写任何字段。
>
> Phase 2 功能不变：integrate_event_and_save / integrate_impression_and_save（中期层）；
>   load_dream_snapshot（只读 bucket 快照，Dream LLM 上下文注入）。
```

---

## 附录：Phase 3 实现顺序建议

```
第1步  实现 apply_time_decay（移除 stub，写测试 AT-*）
第2步  实现 accrue_touch_deficit（移除 stub，写测试 TD-*）
第3步  实现 nudge_embodied_ease（移除 stub，写测试 EE-*）
第4步  实现 reinforce_body_memory（移除 stub，写测试 RM-*）
第5步  实现 consolidate_baselines（移除 stub，写测试 CB-*）
第6步  类型守卫（TypeError 守卫 + _assert_not_long_term，写测试 TG-*）
第7步  integrate_body_cue + integrate_body_cue_and_save（写测试 BC-*）
第8步  调度器 trigger（hidden_state_decay.py，写测试 SC-*）
第9步  Dream snapshot 注入（fetch_context + build_prompt + prune 表，
        run python tests/run_eval.py 验证 tag 激活）
第10步 ARCHITECTURE.md + AGENTS.md 更新，pytest 全套回归
```

每步完成后 pytest 运行全套，确保不回归。

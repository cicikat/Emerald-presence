# D1-IMPL · 梦境 mes_example fallback —— 核实为主（疑似已自然修复）

> 后端（Emerald-presence）。**先核实，别盲改**。文档侧已实查，结论倾向"已不再复现"。
> **前置**：无。**可并行**：随便排。

## 实查结论（文档侧已查）

W0 当初坐实"每轮打 FALLBACK"。再深查发现**数据与加载逻辑现在都是健康的**：

| 检查 | 结果 |
|---|---|
| 各世界包 `mes_example.md` 是否存在/非空 | 全部存在且非空：abo(536) / cat(416) / custom(413) / flower_bud(518) / reality_derived(573) / vampire(604) / 审讯(407) 字节 |
| `_default/mes_example.md` 是否存在 | **存在**（407 字节，6/1 创建） |
| `load_world` 兜底（`world_loader.py:41-83`） | 双重兜底：未知 world_id→`reality_derived`；缺/空 mes_example→`_default/mes_example.md` |
| 活跃默认世界 | `dream_pipeline.py:222` `frozen_world` 默认 `reality_derived`（有 mes_example） |

推论：`dream_prompt.py:268 world = load_world(world_id)` 拿到的 `world.mes_example` **现在恒为非空** → `:308 _mes_from_fallback = not bool(world.mes_example)` **恒为 False** → 不该再打 FALLBACK。

**最可能**：你当初看到的"一直 fallback"是**早期世界包/`_default` 文件尚未补齐时的旧观察**，现在文件齐了，已自然修复。

## CC 要做的（只核实，按结果决定动不动）

1. **运行时确认**：触发一次真实梦境，在 `dream_prompt.py:308` 附近临时 log `world_id` 与 `len(world.mes_example)`。
2. 若 `len>0` 且无 FALLBACK → **直接关闭**，在 `docs/known-issues.md` 记"D1 已随世界包文件补齐自然修复，核实于运行时"。
3. **若仍打 FALLBACK**（与静态分析矛盾）→ 唯一残留嫌疑是 D3 记录路径读到的 `world` 与 `load_world` 返回的不是同一个对象（被覆盖/传错变量）。顺 `dream_prompt.py` 里 `world` 的赋值链查一处即可，**不要去补本就存在的文件**。

## 注意（别误判）

`world_loader.py:66` 的 INFO 日志 `fallback ... field=mes_example source=_default` 是**正常健康兜底**（某世界没自带 mes_example 就用 _default），**不是** D3 的 FALLBACK 标记，别把这条 INFO 当 bug。

## 验收
运行时 log 证明 `world.mes_example` 非空、D3 无 FALLBACK 标记；known-issues 更新结论。

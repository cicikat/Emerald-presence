# Brief 90 · Mirror 模式写回收尾：mode/source 标记 + 门控回流（00e B2）

> 背景：Mirror v0.1 写回全跳（afterglow + impression 双跳，`docs/dream.md` §Mirror）。
> 文档已写明未来契约三条：①impression entry 独立 `mode/source` 标记
> ②`impression_loader` 侧 Reality integrator gate ③显式 WriteEnvelope、不复用
> Sandbox 无标记路径。本单照契约收尾。**Scenario 保持全跳不动**（剧本内容不得进现实，
> 那是设计不是欠账）。

## 1. 🟡 impression entry 加 mode 字段（含存量兼容）

- `distill_impression()` 产出的 entry 增加 `mode: "sandbox" | "mirror"`（来源
  `dream_mode`，scenario 根本不产出）。存量无 mode 字段的旧条目 → 读取时按
  `"sandbox"` 处理（兼容规则写进 loader，不做数据迁移）。
- `_generate_summary_bg()`：`dream_mode == "mirror"` 时不再跳过 `distill_impression()`，
  产出带 `mode="mirror"` 的条目；蒸馏 prompt 对 mirror 增加一条约束：产出**感受性残象**
  （「梦里有种模糊的贴近感」量级），禁止出现倾向材料的桶标签/数值/分析性措辞
  （DM 层三禁令的写回侧对应物）。

## 2. 🟡 impression_loader 的 Reality gate（契约②）

- `load_impression_text()` 增加 mode 感知：
  - `sandbox` 条目：行为完全不变（回归保证）。
  - `mirror` 条目：**不参与出梦强注 3 轮**（forced rounds 只发 sandbox）；话题召回仅在
    tags ∩ {body_intimate, physical_closeness, emotion.deep} 时可命中，且注入文案加
    框定前缀「梦里残留的模糊感觉，不是事实」。
- 6g 层注入格式不变，只是 mirror 条目更难触发、带框定——mirror 反映的是用户隐性状态，
  回流必须比 sandbox 更含蓄，防止变相把 hidden_state 诊断说出口。

## 3. 🟡 mirror afterglow 开闸（契约③）

- `_generate_summary_bg()`：mirror 时恢复调用 `wire_afterglow_from_summary()`，
  `AfterglowResidueInput` 增加 `mode="mirror"` 透传，落盘 residue 带 mode。
- `integrate_afterglow_and_save()` 路径不变（本来就走显式 WriteEnvelope +
  Reality-side integrator，契约③天然满足）；数值影响面维持既有不变量
  （只碰 sensitivity.current / embodied_ease，不碰 baseline/touch_need/body_memory）。
- `dream_afterglow_soft_hint` / `6f_dream_afterglow` 文本层对 mirror 无差别
  （软提示本来就不含内容细节）。

## 4. 🟢 文档同步

`docs/dream.md`：「Mirror v0.1 写回保护」段改写为「Mirror v0.2 门控写回」，
三条未来契约标记为已落地；模式对照表更新。ARCHITECTURE.md hidden_state 注释段
若提及 mirror 候选，同步一句。

## 验收

- sandbox 全链路零回归（无 mode 旧条目按 sandbox 读，强注/召回行为不变）。
- mirror 出梦：impression 带 mode 落盘；**不进**强注 3 轮；无匹配 tag 不召回；
  匹配 tag 召回时带框定前缀。
- mirror afterglow：residue 带 mode、hidden_state 数值变化在既有不变量内
  （断言只动 sensitivity.current / embodied_ease）。
- scenario：仍然双跳（负向回归断言）。
- 蒸馏产物不含桶标签词/数值（对 mirror 蒸馏输出跑禁词断言）。
- `pytest -n auto`。

## Commit 划分

1（entry mode 字段 + 存量兼容）→ 2（loader gate）→ 3（afterglow 开闸）→ 4（文档）。
链式依赖。

# Brief 81 · mood_text 情绪混合文案：用已有 previous/pending 做立体感，零结构改动

> 背景：单情绪标签显得平面。评估结论（DESIGN.md §十一 决策 4）：**否决**多情绪并存 +
> 百分比方案（状态向量化会连锁改 detect prompt、mood_text 映射组合爆炸、episodic
> emotion_bonus、eager 晋升触发、花园情绪槽映射、漂移数学，成本远超收益；文献上
> 连续维度模型 VAD 与离散标签也不该混用同一结构）。**采纳**零结构方案：立体感只在
> 文本层做，`mood_state.json` 已有的 `previous` / `pending` / `intensity` 字段够用。

## 现状

`core/mood_text.py::get_mood_text()` 只消费 `current` + `intensity`（3 档），输出
「他此刻：{描述}」。`previous` 字段落盘但文本层没用；`pending` 只产出固定一句
「但有什么东西好像在悄悄变得不一样」。

## 1. 🟢 混合文案（唯一工单项）

`get_mood_text()` 增加两条规则（纯文本层，不动 schema、不动漂移数学、不动任何消费方）：

- **残留混合**：`previous != current` 且 `previous != "neutral"` 且距 `updated_at`
  未超过 N 轮/时间窗（建议：切换后首个 30 分钟内）→ 在主描述后追加一短句残留，如
  `current=gentle, previous=sad` → 「平静，带一点轻盈。刚才那点沉还没完全散。」
  残留句每情绪一档即可（不做 3 档组合），全表 ≤ 8 句，写在 `MOOD_TEXT` 同文件。
- **pending 保持现状**（那句已经是好的过渡表达），仅当残留句与 pending 句同时触发时
  只保留 pending（避免一层里堆两句情绪旁白）。

实现约束：
- 残留时间窗从 `mood_state.json` 现有 `updated_at` 推，不新增字段。
- `yandere` 不参与残留混合（沿用其 fallback 降级路径，不给它加戏）。
- 输出总长仍受层 1 感知区块的既有篇幅约束，混合后 ≤ 40 字。

## 验收

- `previous=sad, current=gentle`、切换 10 分钟内 → 输出含残留短句；超时间窗 → 不含。
- `previous=neutral` 或 `previous==current` → 行为与现状完全一致（回归）。
- pending 与残留同时满足 → 只出 pending 句。
- 全部消费方（episodic emotion_bonus / nudge / 花园）零改动、零波及（不 touch 即证明）。
- `pytest -n auto`；文档同步 `docs/memory.md` §五 prompt 注入形态一段。

## 明确不做（防范围蔓延）

- 不改 `detect_emotion` 输出格式（仍单标签）。
- 不加情绪百分比/向量、不加新情绪标签、不动强度映射表与漂移公式。
- 若未来仍觉得平面，升级路径是 **valence-arousal 二维连续状态**（单点状态、自然混合），
  而不是多标签百分比——届时另立研究备忘，参考 00d 的流程。

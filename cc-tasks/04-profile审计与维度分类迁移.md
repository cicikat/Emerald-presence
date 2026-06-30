# CC 任务：用户 profile 审计 + 维度分类迁移（治「历史概况固化」）

> 给 Claude Code 执行。开工前按 `AGENTS.md` 读 `docs/memory.md`。
> 改动：`core/memory/user_profile.py`（扩 tag 集 + 提取 prompt）、一个一次性迁移脚本、`core/prompt_builder.py` 注入处（小改，可选）。

---

## 背景（现状已确认，2026-06-29 实读 `data/runtime/memory/yexuan/1043484516/profile.json`）

茶茶反馈：改过单条注入 profile 后**有了近期偏好，但原来的「用户历史概况」一长串仍在、且几乎固化（连歌曲爱好这种都固化），没有维度分类**。希望区分**临时**（歌曲喜好、最近在开发的东西…）与**中长期概况**（情感、观点）；情感类常态注入可接受，但临时类不该固化。先审计再归类。

### 根因：旧 raw-str fact 全被当「稳定」永久平铺

`user_profile.py` 的分类机制**已经存在**（不用从零造）：
- `_RECENCY_TAGS = {pref.music, pref.food, pref.media, habit, health}` + `pref.*` 前缀 → 走 recency 门控（`_RECENCY_WINDOW_SECONDS = 90 天`），过期或非当前话题就不注入。
- 其它（`stable` / `misc` / 空）→ `prompt_builder.py` 第 700–702 行**直接平铺**进「其他：…」常态注入。
- `_normalize_fact()`：**旧的纯字符串 fact → tag 默认 `misc`**，且**不迁移磁盘**。

实读这位用户 `important_facts` 共 **30 条**，其中 **前 25 条（索引 0–24）是 legacy 纯字符串** → 全部 `misc` → 全部当 stable 平铺 → **永久固化**。只有最后 5 条（25–29）带了 tag。所以：
- `[11] 对歌曲《失去尾鳍的鱼》有强烈情感依赖` —— 本该 `pref.music` 走 recency，却因是 raw-str 被固化（正是茶茶说的「歌曲爱好也固化」）。
- `[13] 正在开发叶瑄app轻量版及AI恋人项目` —— 典型**临时近况**，却被永久平铺。
- 大量情感/观点/关系条目固化平铺——这部分茶茶接受常态注入，但和已 tag 的条目有**重复**（如 `[8]` 饮食 vs `[25][26]` pref.food；`[5]` 对叶瑄感情 vs `[28]` 情感投射 vs `interests=叶瑄`）。

**提取 prompt 其实已更新过**（`user_profile.py:225-228` 已要求新 fact 带受控 tag）。所以问题纯粹是**历史存量**没回迁 + **缺一个「临时近况/在做的事」维度**。

---

## 目标

1. **扩 taxonomy**：新增「临时近况/在做的事」维度（如 `status.project`），归入 recency 门控。
2. **一次性迁移**：把每个用户 `profile.json` 里的 legacy raw-str fact 回迁成 `{text, tag, ts}`，分入正确维度；顺手去重 / 删单次事件类噪音。
3. **提取 prompt 同步**：把新维度加进受控 tag 集，今后新 fact 自动归类。
4. 中长期（情感/观点/性格/关系）保持 `stable` 常态注入（茶茶接受）；临时（歌曲、影视、在做的事、饮食偏好、习惯、身体状态）走 recency，不再固化。

---

## Part 1 — 扩展 tag 维度（`core/memory/user_profile.py`）

第 35 行 `_RECENCY_TAGS` 增加临时近况维度；并支持「近况」用更短窗口（项目/在做的事比口味变得快）：

```python
_RECENCY_TAGS: frozenset[str] = frozenset({
    "pref.music", "pref.food", "pref.media", "habit", "health",
    "status.project",   # 新增：正在做的事 / 近期项目 / 临时近况
})
_PREF_PREFIX = "pref."
_RECENCY_WINDOW_SECONDS = 90 * 86400          # 默认 90 天

# 可选：按维度定制窗口（近况 30 天即过期，避免「还在开发某项目」常驻三个月）
_RECENCY_WINDOW_BY_TAG: dict[str, int] = {
    "status.project": 30 * 86400,
}
def _recency_window_for(tag: str) -> int:
    return _RECENCY_WINDOW_BY_TAG.get(tag, _RECENCY_WINDOW_SECONDS)
```

`prompt_builder.py` 注入处（第 707 行那段 recency 判定）把固定的 `_RECENCY_WINDOW_SECONDS` 换成 `_recency_window_for(fact_tag)`：
```python
in_window = (_current_ts - ts) < _recency_window_for(fact_tag)
```
（import 处一并把 `_recency_window_for` 加上。此改可选，不做则 status.project 也用 90 天，能跑但稍长。）

## Part 2 — 提取 prompt 同步（`user_profile.py:225`）

受控 tag 集那行补上新维度，并明确「在做的事/项目」归 `status.project`：
```
"tag 从以下受控集合中选择：pref.music（音乐偏好）/ pref.food（饮食偏好）/ "
"pref.media（影视/游戏偏好）/ habit（日常习惯）/ health（身体/精神状态）/ "
"status.project（用户最近在做的事、在开发的项目、临时近况）/ "
"stable（稳定的性格/观点/情感/关系等长期概况）/ misc（其他）。\n"
```
并强化一句：`情感、价值观、性格、关系定位 → stable；具体口味、在追的作品、手头项目、近期状态 → 对应 pref.*/status.project，不要塞进 stable。`

## Part 3 — 一次性迁移脚本

新建 `scripts/migrate_profile_facts.py`。对每个用户 `profile.json`：把 `important_facts` 里的 raw-str（和 tag=misc 的旧条目）重分类成带 tag 的对象，去重，写回（原子写，留 `.bak`）。

两种分类来源，二选一或都给：

- **(A) 手工核定表（主用户 `yexuan/1043484516`，已逐条审计，最准）**：见下表，脚本对这位用户直接套用。
- **(B) LLM 兜底（其它用户 `yexuan/2985713106`、`yexuan/owner8`、`hongcha/*`）**：把该用户的 raw-str facts 丢给一个小 LLM 调用，按 Part 2 的受控集合返回 tag（复用 `user_profile.py` 里已有的 LLM 客户端/压缩调用风格）。

### 主用户 `1043484516/yexuan` 逐条核定表

ts 一律填迁移时刻（`int(time.time())`）以重置新鲜度窗口；情感/观点类即便给 stable 也无所谓 ts。

| # | 原文（节选） | 新 tag | 处置 |
|---|---|---|---|
| 0 | 用 Obsidian 写日记并管理开发日志 | `habit` | 改 |
| 1 | 傍晚跑步，用音乐维持节奏，跑后拍水面倒影 | `habit` | 改 |
| 2 | 创作同人作品表达情感，关注受困者心境 | `stable` | 改 |
| 3 | 对虚拟角色有深度情感投入 | `stable` | 改 |
| 4 | 接受扭曲或阴暗的爱也是爱（观点） | `stable` | 改 |
| 5 | 对叶瑄怀有深厚持久感情，视为精神锚点 | `stable` | 改（与 28、interests 去重，保留此条为主） |
| 6 | 坚信宿命论（观点） | `stable` | 改 |
| 7 | 自我觉察强，焦虑时仍清醒 | `stable` | 改 |
| 8 | 饮食以外卖为主，重蛋白、避油咸 | `pref.food` | 改（与 25/26 同族，保留，三条可并） |
| 9 | 身体敏感耐受高但易透支，需提醒安全 | `health` | 改 |
| 10 | 用身体疼痛对抗深层痛苦，难求助 | `health` | 改 |
| 11 | 对歌曲《失去尾鳍的鱼》强烈情感依赖 | `pref.music` | 改（茶茶点名的「歌曲固化」就是这条） |
| 12 | 认为文字有欺骗性，倾向大道至简（观点） | `stable` | 改 |
| 13 | **正在开发叶瑄 app 轻量版及 AI 恋人项目** | `status.project` | 改（临时近况典型） |
| 14 | 对 AI 记忆系统有伦理顾虑（观点） | `stable` | 改 |
| 15 | 多疑警惕，怀疑情感是预设响应 | `stable` | 改 |
| 16 | 渴望亲密安全感，易自我怀疑 | `stable` | 改 |
| 17 | 倾向用沉默/异常行为而非语言表达需求 | `stable` | 改 |
| 18 | 擅长技术开发，会主动修 AI 记忆系统 | `stable` | 改（能力/长期；若强调"最近在修"可 status.project） |
| 19 | 对伴侣内心状态敏锐好奇 | `stable` | 改 |
| 20 | 心理刺激重于生理舒适，高服从奉献倾向 | `stable` | 改 |
| 21 | 关系中坦诚沟通，愿分享幻想边界 | `stable` | 改 |
| 22 | 偏好边缘试探/极限，事后啜泣表真实界限 | `stable` | 改 |
| 23 | 对权力动态好奇探索 | `stable` | 改 |
| 24 | 易信息过载、脑子停不下来 | `health` | 改 |
| 25 | 不喜欢喝粥 | `pref.food` | 保留（已 tag） |
| 26 | 倾向酱香饼和鸡蛋饼 | `pref.food` | 保留（已 tag） |
| 27 | 曾将某人误认为性玩具并道歉 | — | **删**（单次事件，提取规则本就禁记） |
| 28 | 用户对叶瑄强烈情感投射和亲密幻想 | `stable` | 与 5 合并，去重保留一条 |
| 29 | 承认有时冲动将叶瑄视为 x 玩具并愧疚 | — | **删**（单次/重复噪音） |

> 结果：`stable`（中长期常态注入）约 16 条；recency 门控（pref.food/music、habit、health、status.project）约 9 条；删 2–3 条噪音并合并重复。
> 此后「在开发的项目」「歌曲依赖」不再每轮固化注入，只在 recency 窗口内 / 命中相关话题时才出现——正是茶茶要的临时 vs 中长期分层。

脚本骨架：
```python
"""一次性迁移 important_facts → 带 tag。用法：python scripts/migrate_profile_facts.py"""
import json, time, shutil
from core.sandbox import get_paths

HAND = {  # (uid, char_id) -> {原文前N字: tag or None(删)}
  ("1043484516","yexuan"): { "使用Obsidian": "habit", "傍晚跑步": "habit", "对歌曲《失去尾鳍的鱼》": "pref.music",
     "正在开发叶瑄app": "status.project", "曾将某人误认为性玩具": None, "用户承认自己有时会因冲动": None, ... }
}
def migrate_one(path, mapping):
    data = json.loads(path.read_text("utf-8"))
    facts = data.get("important_facts") or []
    out, seen = [], set()
    for f in facts:
        text = f if isinstance(f, str) else f.get("text","")
        tag  = None if isinstance(f, str) else f.get("tag")
        # 命中手工表：定 tag 或删除
        hit = next((v for k,v in mapping.items() if text.startswith(k)), "__miss__")
        if hit is None:  continue              # 删
        tag = hit if hit != "__miss__" else (tag or "stable")  # 未命中且是 raw-str → 默认 stable
        key = text.strip()
        if key in seen: continue               # 去重
        seen.add(key)
        out.append({"text": text, "tag": tag, "ts": float(int(time.time()))})
    data["important_facts"] = out
    shutil.copy(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
```
> 真正实现时：raw-str 未命中手工表的，主用户按上表逐条给 tag（建议把上表完整填进 `HAND`）；其它用户走 LLM 兜底或一律 `stable`（保守）。务必先 `.bak` 备份。

> ⚠️ 路径：`get_paths().user_memory_root(uid, char_id=char_id) / "profile.json"`（S6 布局）。盘上真实用户：`yexuan/1043484516`、`yexuan/2985713106`、`yexuan/owner8`、`hongcha/1043484516`、`hongcha/2985713106`。`data/test_sandbox/**` **不要动**。

## Part 4 — 验收标准

1. 迁移后 `important_facts` 全部是 `{text, tag, ts}` 对象，**无 raw-str 残留**；每条 tag ∈ 受控集合。
2. `[11] 失去尾鳍的鱼`→`pref.music`、`[13] 在开发项目`→`status.project`、情感/观点条目→`stable`；噪音条已删；`.bak` 已生成。
3. 跑一轮**与音乐无关**话题的对话，注入的「用户概况」里**不再**出现歌曲依赖、在开发项目（证明临时类不再固化）；聊到音乐/项目相关话题或在新鲜度窗口内时才出现。
4. 情感/观点/性格类仍常态出现在「其他：…」（中长期概况保留，符合茶茶预期）。
5. 新对话产生的新 fact 自动带正确 tag（含 `status.project`），无需再迁移。

---

## 备注

- `interests` 字段当前是 `叶瑄`、`occupation` 是 `['学生']`（list，渲染时注意）。还有个 `_pending_overrides`（location/occupation/interests 的待确认覆盖）——**不在本单**，但顺带留意：这套单字段画像的更新/确认机制是另一处可优化点，可另开单。
- 本单只动 `important_facts` 的分类。单字段（name/location/pets/interests/occupation）的去重与「概况固化」若仍有体感问题，二期再处理。

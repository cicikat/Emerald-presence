# 酒馆（SillyTavern）角色卡适配 — 分析 + CC 实现提示词

> 协作方式：本文件前半部分是**给人看的分析**（你读），后半部分「## 给 CC 的实现任务」是**给 Claude Code 跑的提示词**（你整段丢给 CC）。

---

## 一、两种格式到底差在哪

对比对象：
- 你的卡：`characters/yexuan.json`（Presence 格式，`core/character_loader.py` 解析）
- 酒馆卡：上传的 `2.json`（`spec: "chara_card_v3"`，薛蕴景）

### 1.1 结构层差异：酒馆把真数据放在 `data.*` 里

酒馆 V2/V3 卡是**双层**的：顶层有一份字段（兼容老客户端），**真正生效的数据全在 `data` 对象里**。你的 loader 现在只读顶层 key，喂酒馆卡会读到 `first_mes:"开场白"` 这种占位空壳。

**适配铁律：所有字段都要 `data.get(k) or 顶层.get(k)`，优先 `data`。**

### 1.2 字段映射表

| 酒馆字段（在 `data` 内） | 你的字段 | 能直接对上吗 | 说明 |
|---|---|---|---|
| `name` | `name` | ✅ | 一致 |
| `description` | `description` | ✅ | 一致（你支持 list，酒馆是 str） |
| `personality` | `personality` | ✅ | 酒馆这张是空串，内容全塞进了 description |
| `scenario` | `scenario` | ✅ | 一致 |
| `first_mes` | `first_mes` | ✅ | 一致 |
| `mes_example` | `mes_example` | ✅ | 同样用 `<START>` + `{{user}}/{{char}}` 格式 |
| `system_prompt` | `system_prompt` | ✅ | 一致 |
| `character_book.entries[]` | `world_book[]` | ⚠️ **部分** | 字段名和能力都不同，见 1.3 |
| `alternate_greetings[]` | ❌ 无 | ❌ **缺** | 13 条备用开场白，你只有单条 `first_mes` |
| `post_history_instructions` | ❌ 无 | ❌ **缺** | 「历史之后」注入（越狱/最终约束层） |
| `extensions.depth_prompt` | ≈ author_note | ⚠️ | 按深度注入的提示，你有 author_note 但非按 depth |
| `creator_notes` / `creator` / `character_version` / `tags` | ❌ 无 | 元数据 | 不影响运行，可丢弃或存注释 |
| `extensions.regex_scripts` / `tavern_helper` | ❌ 无 | ❌ 跳过 | 酒馆前端正则替换脚本，运行时特性，不建议移植 |

### 1.3 最大的差距：世界书（character_book vs world_book）

你的 `lore_engine` 只会**按关键词命中**注入（`keywords` 列表 OR 匹配 → 命中才注入），统一注入在一个固定层 `5.5_lore`。

而酒馆这张卡 **17 条里有 14 条 `keys: []` + `constant: true`** —— 也就是**常驻、永远注入**，根本不靠关键词。你现在的引擎对空 keys 条目永远不命中，等于**整张卡的核心人设（体位玩法、基础、爱、状态栏、二次解释……）全部丢失**。这是适配里最致命的一点。

酒馆世界书条目比你多出来的能力：

| 酒馆条目字段 | 作用 | 你有吗 |
|---|---|---|
| `constant: true` | 常驻注入，不看关键词 | ❌ **必须补** |
| `keys[]` | 主关键词（你叫 `keywords`） | ✅ 改名即可 |
| `secondary_keys` + `extensions.selectiveLogic` | 副关键词 + AND/OR/NOT 逻辑 | ❌ 你只有 OR |
| `position: before_char/after_char` + `extensions.position`(0=char前,1=char后,2/3=AN,4=@depth) | 注入位置 | ❌ 你只有一个固定层 |
| `insertion_order` | 排序 | ✅ 一致 |
| `use_regex` / `regex` | 正则匹配 | ✅ 一致（改名 `use_regex`→`regex`） |
| `extensions.probability` | 概率触发 | ❌ 可忽略（按 100% 处理） |
| `prevent_recursion` / `exclude_recursion` | 递归扫描控制 | ❌ 可忽略 |
| `enabled` | 开关 | ✅ 一致 |

### 1.4 你有、酒馆没有的（不用管）

`anniversaries`、`birthday`、`gender`、字段可为数组分段、以及你那套记忆层 —— 这些是你的私货，导入器**保持默认/不填**即可，酒馆卡里本就没有。

### 1.5 结论

- **能 1:1 平移**的：name / description / personality / scenario / first_mes / mes_example / system_prompt。
- **要做转换**的：世界书（重点是 `constant` 常驻 + `position` 位置）。
- **要新增管线层**的：`post_history_instructions`（历史后注入）、`alternate_greetings`（多开场白，至少存下来能选）。
- **可丢弃**的：regex_scripts / tavern_helper / 纯元数据。

---

## 二、适配怎么做（推荐路线）

**两段式**，既快又不动你管线根基：

1. **离线转换器**（主力，1 个脚本）：`scripts/import_st_card.py`，把任意酒馆卡 `xxx.json` 转成你的 `characters/xxx.json`。常驻世界书条目按 `position` 折叠进 description / 一个新的「常驻世界书」块；关键词条目转成你现有的 `world_book[]`。**这一步就能让 90% 的卡跑起来，且不碰管线。**

2. **管线小增强**（可选，让还原度更高）：给 `lore_engine` 加 `constant` 支持、给 prompt_builder 加 `post_history` 层、`alternate_greetings` 落库。能不动就先不动，先用第 1 步跑通。

下面整段提示词直接丢给 CC。

---

## 给 CC 的实现任务

> 把以下内容整段发给 Claude Code。

```
任务：为本项目增加「SillyTavern（酒馆）角色卡导入」能力。

先读 AGENTS.md，再读 core/character_loader.py、core/lore_engine.py、
core/prompt_builder.py（关注 world_book/lore 注入层 5.5_lore、mes_example 层 7、
author_note 相关层），以及 characters/yexuan.json 作为目标格式样例。
参考样例酒馆卡见 docs/ 里我会附的说明；其结构特征如下（chara_card_v3）：
真实数据在 data.* 里；world 书在 data.character_book.entries[]；大量条目是
constant:true 且 keys:[]（常驻注入）。

== 分两个阶段实现，第一阶段必须独立可用 ==

【阶段一：离线转换器（主交付）】
新建 scripts/import_st_card.py，CLI 用法：
    python scripts/import_st_card.py <酒馆卡.json> [--out characters/<id>.json] [--id <id>]

要求：
1. 读取酒馆卡，统一用 `src = data.get("data") or data`（V2/V3 真数据在 data 内，
   缺失字段回退顶层）。spec 不是 chara_card_v2/v3 时按扁平卡处理，给出 warning。
2. 直接平移字段到 Presence 格式（characters/*.json 的结构见 characters/yexuan.json）：
   name, description, personality, scenario, first_mes, mes_example, system_prompt。
   {{char}}/{{user}} 宏原样保留（管线里已有处理）。
3. 转换世界书 data.character_book.entries[] ：
   对每个 entry（跳过 enabled==False、content 为空）：
   - constant==True 或 keys 为空 → 视为「常驻条目」。按位置分流：
       position 含 "before"（before_char / ext.position in {0}）→ 折叠进 description 末尾，
         以 "\n\n[常驻设定:{comment}]\n{content}" 形式追加；
       position 含 "after"（after_char / ext.position in {1,4} 等）→ 收集到一个列表，
         最终拼成一条写入输出 json 的新字段 "post_history_extra"（字符串，
         多条以 "\n\n" 连接，每条带 [comment] 前缀）。
     —— 这样即便不改管线，常驻人设也不会丢（before 进描述，after 暂存待阶段二接入）。
   - 否则（有 keys 的关键词条目）→ 转成 world_book[] 一项：
       { "keywords": entry["keys"], "content": entry["content"],
         "regex": bool(entry.get("use_regex") or entry.get("regex")),
         "insertion_order": int(entry.get("insertion_order",100)),
         "enabled": True }
     secondary_keys/selectiveLogic/probability 暂不支持，若存在则在 stderr 打 warning。
4. 落库 alternate_greetings：原样存为输出 json 的 "alternate_greetings": [...]（list[str]）。
   first_mes 仍取 src["first_mes"]。
5. 落库 post_history_instructions：存为输出 json 的 "post_history_instructions": "..."。
6. 丢弃但记录：creator/creator_notes/character_version/tags 合并成一段写到输出 json 的
   "_import_meta"（dict），并打印来源摘要。regex_scripts/tavern_helper 忽略并 warning。
7. 写文件用 core/safe_write.py 的原子写入；中文不转义（ensure_ascii=False, indent=2）。
8. 打印转换报告：平移了哪些字段、世界书 N 条→常驻 X / 关键词 Y、忽略了什么。

【阶段二：管线接入（在阶段一跑通后再做，改动要小且向后兼容）】
A. core/character_loader.py：在 Character dataclass 增加可选字段
   alternate_greetings: list[str] = []、post_history_instructions: str = ""、
   post_history_extra: str = ""，并在 load() 里 data.get 进来。
   不破坏现有扁平卡（缺省即空）。
B. core/lore_engine.py：让 match() 支持 constant 条目——
   load 时若 entry.get("constant") 为真，标记常驻；match() 返回结果时
   **无条件包含所有常驻条目**（仍按 insertion_order 排序、仍去重）。
   现有关键词逻辑不变。这样未来转换器可不再把 before 常驻折叠进 description，
   但本阶段保持两者兼容。
C. core/prompt_builder.py：新增一个「历史之后」层
   （建议 _layer 命名 "9_post_history"，放在对话历史之后、贴近末尾），
   注入 character.post_history_instructions + character.post_history_extra（非空才加）。
   遵守 docs/prompt-layers.md：新层必须带 _layer 字段，确认 token 裁剪逻辑能看到它。
D. （可选）alternate_greetings：在 admin 或启动选卡处允许选择开场白；不做也行，先存着。

== 验收 ==
- 用我提供的酒馆卡跑转换器，生成 characters/xueyunjing.json，
  人工核对：186cm/桃花眼/梨涡等核心人设在 description 或常驻块里没丢；
  17 条世界书全部有去向（常驻 14 / 关键词 3，数字以实际卡为准）。
- pytest 现有用例全绿；若动了 tag_rules 跑 python tests/run_eval.py。
- 阶段二改了 prompt_builder/lore_engine/character_loader，按 AGENTS.md 同步更新
  对应文档（docs/prompt-layers.md 等），否则 Stop 钩子会拦。
- 不要硬编码 data/ 路径，全部走 core/sandbox.get_paths()。

先只做阶段一，做完给我转换报告，我确认后再让你做阶段二。
```

---

## 三、给你的备注

- 这张薛蕴景卡 14/17 是常驻世界书 —— 这就是为什么不能只做关键词导入，**阶段一里「常驻条目折叠进 description」是保命设计**，先保证人设不丢，再谈还原度。
- `post_history_instructions` 和那些 `after_char` 常驻条目（状态栏、二次解释）是**最影响输出风格**的部分，建议尽量推进到阶段二，否则状态栏/反八股约束的强度会比酒馆里弱。
- 转换器是纯离线脚本、不碰运行时，符合你「CC 跑、风险可控」的协作方式；管线增强可以等转换器跑顺了再分批让 CC 做。

# 酒馆卡适配 · 阶段二 — 管线接入（给 CC 的实现任务）

> 阶段一已完成：`scripts/import_st_card.py` 跑通，`characters/xueyunjing.json` 生成。
> before 常驻块已折进 `description`，after 常驻块进了 `post_history_extra`，关键词条目进 `world_book`。
>
> **但有一个当前问题（阶段二要修的核心）**：转换器写出的 `post_history_extra`
> （薛蕴景这张 5882 字，含「反早退强制指令 / 状态栏写法 / 二次解释」等）
> 现在是**死数据**——`core/character_loader.py` 没加载它，`core/prompt_builder.py` 没注入它。
> 同理 `post_history_instructions`、`alternate_greetings` 也没进管线。
> 阶段二就是把这几样真正接到生成流程里。

把下面整段发给 Claude Code。

```
任务：把已导入的酒馆卡新增字段（post_history_extra / post_history_instructions /
alternate_greetings）接入生成管线。改动要小、向后兼容、不破坏现有扁平卡。

先读 AGENTS.md、docs/prompt-layers.md，再读 core/character_loader.py、
core/prompt_builder.py、core/lore_engine.py。用 characters/xueyunjing.json 当验收样例
（它有 post_history_extra 和 alternate_greetings，没有 post_history_instructions——
因为源卡该字段为空，属正常）。

== 改动 1：character_loader.py 加载新字段（必做）==
在 Character dataclass 增加三个可选字段（放在 gender 之后，保持缺省即空，不破坏老卡）：
    post_history_instructions: str = ""
    post_history_extra: str = ""
    alternate_greetings: list[str] = field(default_factory=list)
在 load() 的 Character(...) 构造里用 data.get 读进来：
    post_history_instructions=data.get("post_history_instructions", ""),
    post_history_extra=data.get("post_history_extra", ""),
    alternate_greetings=data.get("alternate_greetings", []),
注意：现有那段「把 list 字段 join 成 str」的循环只处理
system_prompt/description/personality/scenario。
post_history_instructions / post_history_extra 转换器输出就是 str，无需 join；
alternate_greetings 保持 list[str] 不要 join。
若某张卡的 post_history_* 给的是 list，则也 join 成 str（健壮性，可选）。

== 改动 2：prompt_builder.py 新增「历史之后」注入层（必做，核心）==
位置：在 层11（11_author_note，约 line 1058-1063）/ 11_jailbreak 之后、
层12（12_user_message，约 line 1082）之前，新增层 "11.5_post_history"。
这对应酒馆 Post-History Instructions 的语义：紧贴历史末尾、用户输入之前，影响最大。

实现：
    _ph_parts = []
    if getattr(character, "post_history_instructions", ""):
        _ph_parts.append(character.post_history_instructions)
    if getattr(character, "post_history_extra", ""):
        _ph_parts.append(character.post_history_extra)
    if _ph_parts:
        _layers.append("11.5_post_history")
        messages.append({
            "role": "system",
            "content": "\n\n".join(_ph_parts),
            "_layer": "11.5_post_history",
        })
要求：
- 必须带 _layer 字段（否则 token 裁剪逻辑看不到，见 docs/prompt-layers.md 硬规则）。
- 不要给 _drop_priority —— 这是高价值约束层，应跟 author_note 一样永不被自动裁剪
  （line 1116 注释：无 _drop_priority 的层永不自动丢弃）。
- 用 getattr(..., "") 兜底，确保老卡/缺字段不报错。

== 改动 3：lore_engine.py 支持 constant 常驻条目（可选，低优先）==
背景：当前转换器把常驻条目折进了 description/post_history_extra，所以
xueyunjing.json 的 world_book 里没有常驻条目，本改动对它是 no-op。
做这个是为「未来 pass-through 模式」（见改动 4）铺路，让常驻条目能原样走世界书层。
实现（保持现有关键词逻辑完全不变，只做加法）：
- _process_entry：在归一化结果里保留 "constant": bool(entry.get("constant", False))。
- match()：返回结果时，**无条件包含所有 constant==True 的条目**
  （不看关键词命中），仍按 insertion_order 排序、仍参与现有去重（seen 集合）。
若不确定影响面，本改动可以先跳过，只做改动 1、2、5。

== 改动 4：转换器加 --passthrough-lore 开关（可选，低优先）==
给 scripts/import_st_card.py 加 --passthrough-lore：开启时，常驻条目不再折进
description/post_history_extra，而是原样写进 world_book[]，带
{"constant": true, "content":..., "insertion_order":..., "keywords":[], "position":...}。
默认关闭，保持阶段一行为不变。仅在改动 3 落地后才有意义。

== 改动 5：alternate_greetings 落到 Character 即可（必做一半）==
改动 1 已把 alternate_greetings 读进 Character。本步只要求「存下来、可访问」，
不要求改选卡 UI。若 admin 选卡处容易加一个「随机/指定开场白」选项就加，
不方便就保持 first_mes 现状，alternate_greetings 先躺在 Character 上备用。
不要为此大改 admin 流程。

== 验收 ==
1. 写个临时脚本或 pytest 用例：load("xueyunjing") 后断言
   character.post_history_extra 非空、alternate_greetings 长度==13。
2. 构造一次 build_prompt（可参考现有 prompt 相关测试的调用方式），断言
   返回的 messages 里存在 _layer=="11.5_post_history" 的一条，且其 content
   含薛蕴景 post_history_extra 里的特征串（如「严禁简略与早退」）。
3. pytest 全绿。没动 tag_rules.py 就不必跑 run_eval；但**动了 prompt_builder
   就必须按 AGENTS.md / Stop 钩子更新 docs/prompt-layers.md**：补上层 11.5_post_history
   的说明（位置、来源字段、不参与裁剪）。
4. 不硬编码 data/ 路径；新层注入逻辑用 getattr 兜底，确保 yexuan.json 等老卡
   （无这些字段）构建 prompt 不报错、行为不变。

先做改动 1、2、5（核心三件），跑通验收 1-3 给我看结果；改动 3、4 等我确认后再做。
```

---

## 给你的备注

- **改动 2 是这次的命门**：把 `post_history_extra` 接进层 11.5。接上之后，薛蕴景那套
  「反早退 / 状态栏像记录别像散文 / 二次解释」才真正生效，输出风格会明显更贴酒馆原卡。
- 改动 3、4 是「常驻条目走世界书层」的另一条技术路线，和阶段一「折进 description」是
  二选一关系。阶段一的方案已经能跑，所以 3、4 标了低优先——**先把死数据救活（1/2/5），
  还原度不够再考虑换路线**。
- 我让 CC 先交核心三件、跑验收再停，跟你「分批、风险可控」的节奏一致。

# X3 · 叶瑄自己上网 + 自建库 + 自检索（决策已替你拍 + MVP 工单）

> 后端（Emerald-presence）。**决策类，但你授权我拍板**——本文已替你圈好 MVP 范围，CC 按「MVP 改动点」施工，越界的（完全自主浏览）明确划在范围外。
> **前置**：X1 向量库（✓ 已落地，存储/embedding 已统一）。与 TOY 自主写入同源。
> **可并行**：与注入簇/梦境簇无冲突；与 TOY、X2 共用 `vector_store`，建议排在 X1 验收稳定之后。

## 现状（已核对）

`core/tools/web_search.py`：`ddgs` 文本搜索，max_results=3，返回拼接文本。**纯反应式、用完即弃**——搜了不留、不可检索、不自主。距离你说的"自己上网、自己做数据库、自己检索"差三步。

## 决策：MVP 范围（我替你定）

把"自主上网"拆成**能跑通的最小闭环**，先要"留得下、查得回"，再谈"多聪明"：

1. **搜（已有）**：复用 `web_search.search`。
2. **留（新）**：搜索结果 `vector_store.upsert(source="web", source_id=url, ts, text)`——叶瑄搜过的东西**沉淀进同一套向量库**，形成"她自己的资料库"。这就是「自建库」，和 TOY 自主写入、X1 共用一个 store。
3. **查（新）**：之后相关 query 命中 `vector_store.query(sources=["web"])`，语义召回她查过的资料。这就是「自检索」。
4. **自主触发（克制版）**：叶瑄在"想知道但不确定"时**自行**发起一次搜索（author_note 给软提示 + 探针允许调用 `web_search`），**限频**（配置 `web_autosearch.min_interval_min`，默认 30）。

### 明确划在 MVP 外（别做）

- 完全自主浏览网页正文 / 点链接 / 多跳爬取——风险与复杂度高，本期不做。
- 只做"搜索摘要 → 沉淀 → 语义检索"，不做"打开任意 URL 读全文"。

## MVP 改动点

1. `web_search.search` 调用处加 `vector_store.upsert(source="web", source_id=<url>, ts=now, text=<title+snippet>)`。去重靠 vec_meta(source,source_id=url)。
2. 召回侧（X2 的 `score_recall` 链）允许 `sources` 含 `"web"`，让 web 资料和记忆一起参与召回（但**打 `web` 来源标签**，注入时框为"她查到的资料"而非"她的记忆/经历"——别让外部事实污染人格记忆，比照 D2 的隔离精神）。
3. 自主触发：author_note 软提示 + 探针 `web_search` 可用 + 限频；总开关 `web_autosearch.enabled`（默认关，你开）。

## 安全/隔离

- web 内容是**外部事实**，不是叶瑄的经历——注入框定为"查到的资料"，**不进 episodic/identity 固化**（同 D2 隔离墙思路：consolidation 跳过 web 来源）。
- 沿用 AGENTS 出站代理规则（web_search 已处理 proxy）。

## 验收

1. 叶瑄搜一次 → `vector_store` 里出现 `source="web"` 条目（去重按 url）。
2. 之后相关提问 → 能语义召回这条 web 资料，且注入框为"查到的"。
3. 自主触发限频生效；开关关掉退回纯反应式搜索。
4. web 事实不混进 episodic/identity。

## 文档同步
`docs/` 新增 X3 资料库段；`AGENTS.md` 工具系统补 web 自主搜索与隔离规则。

> 注：本工单是 MVP。"更自主的浏览"若以后要做，单开 X3-phase2，先把这个闭环跑稳。

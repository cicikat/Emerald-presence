# C1 根目录资产盘点（迁移前清单）

> 盘点日期：2026-07-22。此文件是 C1 的第一阶段产物：**只记录决策，不移动、不删除、不改路径引用**。
> 第二阶段必须在用户审阅本清单、并手动完成下文“需手动删除”项后再开始。

## 决策与目标结构

后续将新增一个仅容纳用户私有 authored 资产的根目录：`userdata/`。它不承载
`data/` 的运行时状态；后者继续由 `core.sandbox.get_paths()` 管理，并保持测试沙箱偏移。

```text
userdata/                         # 后续新增；用户可写/私有 authored 资产
├── assets/stickers/
└── characters/
    ├── cards/
    ├── authored/{char_id}/
    ├── reality/
    └── dream/{presets,worlds}/
```

迁移实现会先提供 `userdata/` 主路径与现有路径只读回退；不会在未验证引用和回退观测前删除旧资产。

## 保留在根目录

| 路径 | 判定 | 依据 |
|---|---|---|
| `admin/`、`channels/`、`core/`、`scripts/`、`tests/`、`tools/`、`firmware/` | 保留 | 源码、测试与构建入口。 |
| `data/` | 保留 | 运行时 canonical 状态根；必须经 `get_paths()` 并在 test mode 偏移。不是可随意迁移的用户素材目录。 |
| `defaults/` | 保留 | 8 个已跟踪 seed 文件；`DataPaths` 使用它们初始化空运行时状态。 |
| `examples/` | 保留 | 已跟踪的公开角色卡示例/模板。 |
| `content/characters/default/`、`content/jailbreak_presets/示例.example.json` | 保留 | 已跟踪的公开默认 authored 资产。 |
| `characters/default.json`、`characters/default_author_notes.json` | 保留 | 已跟踪的公开默认角色卡与作者注池。 |
| `characters/dream_postcards/templates/` | 保留 | 已跟踪的 Dream 明信片模板；`core/dream/postcard.py` 直接读取。 |
| `config.example.yaml`、`*.example.yaml`、`secrets.example.yaml`、`README*`、`ARCHITECTURE.md`、`AGENTS.md`、`DESIGN.md`、启动/安装脚本 | 保留 | 项目文档、模板和启动入口；即使某些本地文档当前未跟踪，也不是缓存。 |
| `config.yaml`、`secrets.local.yaml` | 保留在根目录且继续忽略 | 本机运行配置/凭据；不能提交、移动或删除。 |

## 后续迁入 `userdata/`（本阶段不移动）

| 当前路径 | 目标路径 | 当前消费者/原因 |
|---|---|---|
| `assets/stickers/` | `userdata/assets/stickers/` | 私有贴纸库；当前由 `core/output/sticker.py` 读取。 |
| `characters/*.json`（排除 `default.json` 与 `default_author_notes.json`） | `userdata/characters/cards/` | 私有角色卡；当前由 `core/character_loader.py`、`core/asset_registry.py` 和角色管理 API 扫描。 |
| `characters/{char_id}_author_notes.json`（非 default） | `userdata/characters/authored/{char_id}/author_notes.json` | 私有作者注池；当前有 `DataPaths.author_notes_pool()` 兼容读取。 |
| `content/characters/{char_id}/`（排除 `default/` 与 `*.example.*`） | `userdata/characters/authored/{char_id}/` | 私有 traits、activity pool、信件、知识库、参考音频；当前由 `DataPaths` authored accessor 使用。 |
| `characters/reality/` | `userdata/characters/reality/` | 私有 reality lorebook、jailbreak 与头像资产；当前由 `DataPaths`、asset registry、prompt builder 使用。 |
| `characters/dream_presets/`、`characters/dream_worlds/` | `userdata/characters/dream/{presets,worlds}/` | 私有 Dream 世界/预设；当前由 Dream loaders 与 asset registry 使用。 |

迁移时须同步完成：`core/data_paths.py` / `core/asset_registry.py` / `core/character_loader.py` /
Dream loaders / `core/output/sticker.py` 的统一访问器改造，补充旧路径回退及其命中观测，并更新
`.gitignore`、`docs/data-taxonomy.md`、相应测试。不得把任何 `data/` 路径迁到本目录。

## 需由用户手动删除

这些路径均未被 Git 跟踪，且没有业务代码将其作为资产根读取。请在没有 pytest、服务或固件构建正在运行时手动删除；删除后告诉我即可。

| 路径 | 原因 |
|---|---|
| `MagicMock/` | 测试 mock 对象误写到仓库根目录的残留。 |
| `__pycache__/` 及所有 `**/__pycache__/` | Python 字节码缓存。 |
| `.pytest_cache/` | pytest 缓存。 |
| `.tmp/` | Codex/pytest 临时目录；仅在确认没有活跃测试后删除。 |
| `.claude/.cache/` | 本地编辑历史缓存。 |
| `firmware/presence-device/.pio/` | PlatformIO 构建产物。 |

`firmware/presence-device/.vscode/` 为本机编辑器配置，不列为必删项；是否删除由用户自行决定。

## 第二阶段准入检查

开始迁移前必须同时满足：

1. 用户已确认本清单，且上述手动删除项已处理或明确保留；
2. `git status --short` 无意外改动；
3. 所有迁移源、目标和 fallback 路径经测试覆盖；
4. 未将 `config.yaml`、`secrets.local.yaml`、`data/` 或公开 default/example 资产纳入移动/删除范围。

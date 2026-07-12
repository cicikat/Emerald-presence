# Brief 56 · 视觉感知源：本地 VLM 观察 + shadow 模式（阶段 1）

> 依赖：无（与 Stage 系列、57 均可并行）。**默认全关**，配置显式开启才生效。
> 参考：Screenpipe 的 redaction 设计；VLM 个人影像过度推断 benchmark（arXiv 2511.02367）；
> HEARTBEAT 静默记忆污染（arXiv 2603.23064）。
> 目标：为"图像 → 生活轨迹 → 习惯记忆"打地基。本单只做**感知与观测**，
> 零记忆写入——shadow 模式观察 VLM 幻觉率，数据合格后另立工单接 fixation 链。

## 1. VLM adapter（新文件 core/perception/vlm_client.py）

- 仿 `core/memory/embedding.py` 边界哲学：唯一对外接口
  `async describe(image_bytes, context_hint) -> VisualObservation | None`。
- Provider：`config.yaml` 新增 `visual_perception:` 块
  （`enabled: false` 默认 / `base_url` / `model` / `api_key` / `timeout_s: 20`），
  OpenAI-compat vision 接口（用户后期部署本地模型，同协议直连）。
- 失败/超时/enabled=false → 返回 None，fail-open，永不阻塞任何主链路。

## 2. 观察 schema（受控枚举，防自由文本幻觉）

VLM prompt 要求输出纯 JSON：

```json
{
  "scene": "desk|away|bed|meal|outdoor|other",
  "activity": "working|gaming|watching|reading|phone|idle|unknown",
  "confidence": 0.0-1.0,
  "sensitive": false,
  "caption": "≤30字中文描述"
}
```

- `scene` / `activity` 枚举校验 fail-closed：非法值/坏 JSON → 整条丢弃，记 WARN。
- `sensitive=true`（画面含支付/密码/证件等）→ **丢弃整条，什么都不存**；
  prompt 里把敏感判定放第一优先级。
- 图像本体**永不落盘**——处理完即丢，只存结构化观察。

## 3. 接入端点（admin/routers/perception.py，新增）

`POST /perception/visual`：multipart 图像 + `source` 字段（`screen` / `camera`）。

- scope：`sensor.write`（scopes 表现成，sensor-service/ESP32 的 profile 已含）。
- 限频：同 source 冷却 5 分钟（常量），冷却内直接 202 丢弃，防抓帧端打爆 VLM。
- 处理为 `asyncio.create_task` 后台执行，端点立即返回（VLM 20s 超时不挡上传方）。

## 4. shadow trace（唯一落盘物）

`data/runtime/perception/visual_trace.jsonl`（经 data_paths 新增访问器，Hard Rule 1；
`safe_append_jsonl`；保留 30 天，滚动清理仿 event_log）：

```json
{"ts": ..., "source": "screen", "scene": "desk", "activity": "working",
 "confidence": 0.8, "caption": "...", "dropped": null}
```

被丢弃的帧也记一行（`dropped: "sensitive" | "invalid" | "cooldown" | "vlm_error"`，
不含任何内容字段）——幻觉率和丢弃率都要可观测。

新增 `scripts/audit_visual_trace.py`：按天输出 scene/activity 分布、confidence 直方图、
丢弃原因统计，供人工抽查对照真实作息。

## 5. 拍板

- **本单零记忆写入**：不碰 short_term / mid_term / episodic / identity / hidden_state /
  prompt 层。接 fixation 固化习惯是下一张工单，准入条件 = shadow 跑 ≥2 周、
  人工抽查 caption 幻觉率 < 10%、sensitive 漏判 0 例。
- 抓帧端（桌面客户端截屏 / ESP32 摄像头）属 Emerald-client / firmware 侧，
  本单只管后端收口；变化检测触发抓帧的建议写进端点 docstring 供客户端侧参考。
- 冷却 5min、保留 30 天、caption 30 字全部命名常量。

## 6. 测试

1. enabled=false → 端点 202 但零处理零落盘。
2. 合法观察 → trace 一行；坏 JSON / 非法枚举 → dropped=invalid；sensitive → dropped 行不含 caption。
3. 冷却：5 分钟内第二帧 → dropped=cooldown，不调 VLM（mock 断言零调用）。
4. VLM 超时 → dropped=vlm_error，端点上传方无感知。
5. 无 `sensor.write` scope → 403（复用 test_sec_auth2 模式）。
6. 图像不落盘：处理后临时文件/内存无残留路径（负向断言）。

## 7. 不做什么

- 不写任何记忆层、不注入任何 prompt 层（下一单的事）。
- 不做 OCR / 屏幕文字提取（screen_awareness 3.9 层已有窗口标题路径，不重复）。
- 不存原图、不存视频、不做时间轴回放 UI。

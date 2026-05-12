"""
手机传感器数据接收路由（口袋角色）
接收来自手机APP推送的传感器数据，存入用户画像供角色感知。

数据格式（POST /sensor/push）：
  {
    "steps": 3200,
    "battery": 85,
    "location": "杭州",
    "screen_sessions": 12,
    "timestamp": 1714000000
  }

无需鉴权，内网使用，不建议暴露公网。
"""

import json
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException
from core.config_loader import get_config
from core.memory.user_profile import load as _load_profile, save as _save_profile
from core.sandbox import get_paths

router = APIRouter()

# 最近一次手机传感器快照（内存缓存，重启清零）
_last_sensor_data: dict = {}


def _save_sensor_to_profile(data: dict):
    """把传感器数据聚合后存入用户画像"""
    oid = str(get_config().get("scheduler", {}).get("owner_id", ""))
    if not oid:
        return

    profile = _load_profile(oid)

    # 存入 phone_sensor_log，保留最近30条
    log = profile.get("phone_sensor_log", [])
    log.append({
        "time":            datetime.now().strftime("%Y-%m-%d %H:%M"),
        "steps":           data.get("steps"),
        "battery":         data.get("battery"),
        "location":        data.get("location"),
        "screen_sessions": data.get("screen_sessions"),
    })
    profile["phone_sensor_log"] = log[-30:]

    # 聚合今日摘要，角色读的是这个，不是原始流水
    today = datetime.now().strftime("%Y-%m-%d")
    summary = profile.get("phone_sensor_today", {})

    # 步数取最大值（今日累计）
    if data.get("steps") is not None:
        summary["steps"] = max(summary.get("steps", 0), data["steps"])

    # 电量记录最新值
    if data.get("battery") is not None:
        summary["battery"] = data["battery"]

    # 位置记录最新值
    if data.get("location"):
        summary["location"] = data["location"]

    # 亮屏次数取最大值
    if data.get("screen_sessions") is not None:
        summary["screen_sessions"] = max(summary.get("screen_sessions", 0), data["screen_sessions"])

    summary["date"] = today
    summary["last_updated"] = datetime.now().strftime("%H:%M")
    profile["phone_sensor_today"] = summary

    _save_profile(oid, profile)


@router.post("/sensor/push", summary="接收手机传感器数据")
async def receive_sensor_data(body: dict):
    """
    手机APP每30分钟推送一次传感器数据。

    body字段（均可选，有什么传什么）：
      steps          — 今日步数
      battery        — 当前电量（0-100）
      location       — 城市名（可选）
      screen_sessions — 今日亮屏次数
      timestamp      — 时间戳（可选，不传用服务器时间）
    """

    # 基础校验
    steps = body.get("steps")
    battery = body.get("battery")

    if steps is not None:
        try:
            steps = int(steps)
            if steps < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="steps 必须为非负整数")

    if battery is not None:
        try:
            battery = int(battery)
            if not (0 <= battery <= 100):
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="battery 必须为 0-100 的整数")

    data = {
        "steps":           steps,
        "battery":         battery,
        "location":        str(body.get("location", "")).strip() or None,
        "screen_sessions": body.get("screen_sessions"),
    }

    # 更新内存快照
    _last_sensor_data.clear()
    _last_sensor_data.update({
        **data,
        "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 存入用户画像
    _save_sensor_to_profile(data)

    return {"message": "传感器数据已接收", "data": data}


@router.get("/sensor/status", summary="获取最近一次手机传感器快照")
async def get_sensor_status():
    """返回最近一次推送的传感器数据快照"""
    return _last_sensor_data


@router.get("/sensor/today", summary="获取今日传感器聚合摘要")
async def get_sensor_today():
    """返回今日聚合摘要，角色的context读这个"""
    oid = str(get_config().get("scheduler", {}).get("owner_id", ""))
    if not oid:
        return {}
    profile = _load_profile(oid)
    return profile.get("phone_sensor_today", {})


@router.post("/sensor/activity", summary="接收桌宠端活动快照")
async def receive_activity_snapshot(payload: dict):
    """桌宠端每5分钟推送一次屏幕活动快照，写入文件供 prompt_builder 读取。"""
    payload["received_at"] = time.time()
    p = get_paths().activity_snapshot()
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok"}

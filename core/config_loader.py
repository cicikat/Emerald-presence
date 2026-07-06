"""
配置加载模块
全局单例，读取 config.yaml，供所有模块使用
"""

import yaml
from pathlib import Path

_config: dict | None = None
_CONFIG_PATH = Path("config.yaml")
_config_mtime: float | None = None


def get_config() -> dict:
    """
    返回配置字典（单例，带 mtime 热加载）。
    每次调用 stat() config.yaml；若 mtime 较上次加载时变化（或从未加载过），
    自动 reload_config()。stat() 开销可忽略，使手改 config.yaml 对运行中进程即时生效
    （此前 _config 是永久缓存单例，手改磁盘文件从不被运行中进程读取）。
    stat 失败（如文件被临时替换的极短窗口）时 fail-open：沿用内存缓存，不抛出。
    """
    global _config
    if _config is None:
        reload_config()
        return _config
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
    except OSError:
        return _config
    if mtime != _config_mtime:
        reload_config()
    return _config


def reload_config() -> dict:
    """重新从磁盘读取 config.yaml（admin 修改或磁盘 mtime 变化后调用）"""
    global _config, _config_mtime
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
        _config_mtime = _CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        raise RuntimeError(f"配置文件不存在：{_CONFIG_PATH.absolute()}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"配置文件格式错误：{e}")
    return _config


def _char_name() -> str:
    return get_config().get("character", {}).get("name", "他")


def get_user_display_name() -> str:
    """用户显示名（config.yaml → user.display_name），未配置时返回空串。

    调用方在空值时应回退到无名称写法（例如直接省略称呼、只用"你"），
    不得拼出"用户（）"这类怪句。"""
    return str(get_config().get("user", {}).get("display_name") or "").strip()

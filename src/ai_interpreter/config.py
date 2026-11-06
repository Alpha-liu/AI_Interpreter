# -*- coding: utf-8 -*-
"""全局配置：从用户配置文件读写 API_KEY / WORKSPACE_ID / MODEL / WS_URL。

配置文件位置优先级（首个可写目录）：
    1. %APPDATA%/ConferenceInterpreter/config.json
    2. ~/.conference_interpreter/config.json
    3. ./user_config/config.json   （兜底：便携模式）

首次运行时文件不存在，使用内置默认值；用户点"设置 → 保存"后才落盘。
"""

import os
import json
from pathlib import Path


# ============================================================
# 内置默认值（可改，作为"出厂设置"）
# ============================================================
DEFAULT_WS_URL = "wss://ws-f2u9w7cxffmu7t9h.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"
DEFAULT_MODEL = "qwen3-asr-flash-realtime"
DEFAULT_API_KEY = ""          # 留空：首次运行强制用户去设置里填
DEFAULT_WORKSPACE_ID = ""     # 留空：按服务商要求填写

#WS_URL = f"wss://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model={MODEL}"

_DEFAULTS = {
    "api_key": DEFAULT_API_KEY,
    "workspace_id": DEFAULT_WORKSPACE_ID,
    "model": DEFAULT_MODEL,
    "ws_url": DEFAULT_WS_URL,
}


# ============================================================
# 配置目录与文件定位
# ============================================================
def _user_config_dir() -> Path:
    """优先 %APPDATA%，依次回退，保证目录可写。"""
    candidates = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "ConferenceInterpreter")
    candidates.append(Path.home() / ".conference_interpreter")
    candidates.append(Path.cwd() / "user_config")

    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    return Path.cwd()


_CONFIG_FILE = _user_config_dir() / "config.json"
_user_cfg = dict(_DEFAULTS)


def get_config_file() -> str:
    """供设置对话框展示当前配置文件路径。"""
    return str(_CONFIG_FILE)


# ============================================================
# 加载 / 保存 / 重载
# ============================================================
def load_config() -> dict:
    """从磁盘读取配置文件并应用到模块级变量。"""
    global _user_cfg
    cfg = dict(_DEFAULTS)
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in _DEFAULTS:
                    if k in data and data[k] is not None:
                        cfg[k] = data[k]
        except Exception as e:
            print(f"[config] 读取配置文件失败，使用默认值: {e}")
    _user_cfg = cfg
    _apply()
    return dict(cfg)


def save_config(**updates) -> bool:
    """把关键字参数写入配置文件，并即时刷新模块级变量。"""
    cfg = dict(_user_cfg)
    for k, v in updates.items():
        if k in _DEFAULTS and v is not None:
            cfg[k] = v
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"[config] 配置已保存: {_CONFIG_FILE}")
    except Exception as e:
        print(f"[config] 保存配置失败: {e}")
        return False

    _user_cfg.clear()
    _user_cfg.update(cfg)
    _apply()
    return True


def reload() -> dict:
    """显式重载（save_config 内部已自动重载，此处供外部冗余调用）。"""
    return load_config()


# ============================================================
# 鉴权 header 构造（各服务商可能不同，改这一个函数即可）
# ============================================================
def build_auth_headers(api_key: str, workspace_id: str = "") -> list:
    headers = [f"Authorization: Bearer {api_key}"]
    if workspace_id:
        headers.append(f"X-DashScope-WorkSpace: {workspace_id}")  # 修正此处
    return headers


# ============================================================
# 模块级变量：初始为默认值，import 时同步一次磁盘配置
# ============================================================
API_KEY = DEFAULT_API_KEY
WORKSPACE_ID = DEFAULT_WORKSPACE_ID
MODEL = DEFAULT_MODEL
WS_URL = DEFAULT_WS_URL


def _apply():
    """把 _user_cfg 刷到模块级变量，供各处直接读取。"""
    global API_KEY, WORKSPACE_ID, MODEL, WS_URL
    API_KEY = _user_cfg.get("api_key", DEFAULT_API_KEY)
    WORKSPACE_ID = _user_cfg.get("workspace_id", DEFAULT_WORKSPACE_ID)
    MODEL = _user_cfg.get("model", DEFAULT_MODEL)
    WS_URL = _user_cfg.get("ws_url", DEFAULT_WS_URL)


# import 时自动加载一次
load_config()


# ============================================================
# 目标语言表（用户界面下拉框用）
# ============================================================
# 若你的服务商支持更多/更少的语言，直接增删即可。
TARGET_LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
    "ar": "العربية",
    "th": "ไทย",
    "vi": "Tiếng Việt",
}


# ============================================================
# 字幕显示配置对象（每路会话一个实例）
# ============================================================
class SubtitleConfig:
    """描述一路翻译会话的字幕显示/翻译行为。"""

    def __init__(self, target_lang: str):
        self.target_lang = target_lang
        self.show_source = True
        self.show_target = True

    def __repr__(self):
        return (f"SubtitleConfig(target_lang={self.target_lang!r}, "
                f"show_source={self.show_source}, "
                f"show_target={self.show_target})")
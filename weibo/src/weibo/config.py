"""Configuration loading with environment variable precedence."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from weibo.errors import ConfigError

PRESET_PROMPTS: dict[str, str] = {
    "h2v": (
        "以 9:16 竖屏比例重新构图，严格保持原视频的全部动作、表演、"
        "镜头运动和节奏不变，仅调整画面构图比例，主体居中。"
    ),
    "style_transfer": (
        "保持原片镜头运动与表演节奏，将画风转换为指定风格，"
        "角色造型与场景氛围与原片一致。"
    ),
    "character_swap": (
        "保持原片镜头运动、场景与叙事节奏，将角色替换为指定形象，"
        "动作、表情与交互关系与原片一致。"
    ),
    "viral_replica": (
        "复刻原片的镜头语言、节奏与视觉风格，以 9:16 竖屏构图输出，"
        "主体居中偏上，画面饱满有冲击力。"
    ),
}

PRESET_RATIOS: dict[str, str] = {
    "h2v": "9:16",
    "viral_replica": "9:16",
}


@dataclass
class AppConfig:
    api_key: str
    base_url: str = "https://ark.cn-beijing.volces.com"
    video_submit_endpoint: str = "/api/v3/contents/generations/tasks"
    video_status_endpoint_template: str = "/api/v3/contents/generations/tasks/{task_id}"
    video_model: str = "doubao-seedance-2-0-260128"
    video_ratio: str = "9:16"
    video_duration: int = 15
    segment_seconds: int = 15
    request_timeout_s: int = 120
    poll_interval_s: int = 10
    poll_max_wait_s: int = 1800
    tos_access_key: str = ""
    tos_secret_key: str = ""
    tos_bucket: str = ""
    tos_endpoint: str = "tos-cn-beijing.volces.com"
    tos_region: str = "cn-beijing"

    @property
    def tos_available(self) -> bool:
        return bool(self.tos_access_key and self.tos_secret_key and self.tos_bucket)


def load_config(*, overrides: dict[str, Any] | None = None) -> AppConfig:
    overrides = overrides or {}

    for candidate in [Path.cwd(), *Path.cwd().parents]:
        env_file = candidate / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
            break

    api_key = (
        overrides.get("api_key")
        or os.getenv("WEIBO_ARK_API_KEY")
        or os.getenv("CHANGDU_ARK_API_KEY")
        or os.getenv("ARK_API_KEY")
    )
    if not api_key:
        raise ConfigError(
            "Missing API key. Set WEIBO_ARK_API_KEY, CHANGDU_ARK_API_KEY, or ARK_API_KEY."
        )

    merged: dict[str, Any] = {
        "api_key": api_key,
        "base_url": os.getenv(
            "WEIBO_ARK_BASE_URL", "https://ark.cn-beijing.volces.com"
        ),
        "video_model": (
            os.getenv("WEIBO_SEEDANCE_ENDPOINT")
            or os.getenv("CHANGDU_SEEDANCE_ENDPOINT")
            or "doubao-seedance-2-0-260128"
        ),
        "request_timeout_s": int(os.getenv("WEIBO_REQUEST_TIMEOUT", "120")),
        "poll_interval_s": int(os.getenv("WEIBO_POLL_INTERVAL", "10")),
        "poll_max_wait_s": int(os.getenv("WEIBO_POLL_MAX_WAIT", "1800")),
        "tos_access_key": os.getenv("VOLC_ACCESSKEY", ""),
        "tos_secret_key": os.getenv("VOLC_SECRETKEY", ""),
        "tos_bucket": os.getenv("WEIBO_TOS_BUCKET", ""),
        "tos_endpoint": os.getenv("WEIBO_TOS_ENDPOINT", "tos-cn-beijing.volces.com"),
        "tos_region": os.getenv("WEIBO_TOS_REGION", "cn-beijing"),
    }
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return AppConfig(**merged)

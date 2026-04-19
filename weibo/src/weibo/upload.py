"""Upload local files to Volcengine TOS and return public URLs."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import tos

from weibo.errors import ConfigError


@dataclass
class TOSConfig:
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str = "tos-cn-beijing.volces.com"
    region: str = "cn-beijing"


def load_tos_config() -> TOSConfig:
    ak = os.getenv("VOLC_ACCESSKEY", "")
    sk = os.getenv("VOLC_SECRETKEY", "")
    bucket = os.getenv("WEIBO_TOS_BUCKET", "")
    if not (ak and sk and bucket):
        raise ConfigError(
            "TOS 上传需要设置 VOLC_ACCESSKEY、VOLC_SECRETKEY、WEIBO_TOS_BUCKET。"
        )
    return TOSConfig(
        access_key=ak,
        secret_key=sk,
        bucket=bucket,
        endpoint=os.getenv("WEIBO_TOS_ENDPOINT", "tos-cn-beijing.volces.com"),
        region=os.getenv("WEIBO_TOS_REGION", "cn-beijing"),
    )


def upload_file(local_path: Path, *, prefix: str = "weibo/", tos_cfg: TOSConfig | None = None) -> str:
    """Upload a local file to TOS and return the public URL."""
    cfg = tos_cfg or load_tos_config()
    client = tos.TosClientV2(
        cfg.access_key, cfg.secret_key, cfg.endpoint, cfg.region,
        connection_time=30,
        socket_timeout=300,
    )

    unique = uuid.uuid4().hex[:8]
    key = f"{prefix}{unique}_{local_path.name}"

    client.put_object_from_file(cfg.bucket, key, str(local_path))

    url = f"https://{cfg.bucket}.{cfg.endpoint}/{key}"
    return url

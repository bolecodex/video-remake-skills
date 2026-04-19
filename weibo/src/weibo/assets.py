"""Volcengine Ark Assets API client for managing trusted media assets.

Assets allow real-person videos to bypass content safety checks by
registering them as trusted assets first, then referencing them via
``asset://<asset_id>`` URIs in Seedance requests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx


class AssetsClient:
    SERVICE = "ark"
    VERSION = "2024-01-01"
    HOST = "open.volcengineapi.com"

    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing") -> None:
        self.ak = access_key
        self.sk = secret_key
        self.region = region

    # ── public API ──────────────────────────────────────────────

    def create_asset_group(self, name: str, description: str = "", group_type: str = "AIGC") -> str:
        body = {"Name": name, "Description": description, "GroupType": group_type}
        resp = self._call("CreateAssetGroup", body)
        result = resp.get("Result", resp)
        return result["Id"]

    def create_asset(
        self, group_id: str, url: str, asset_type: str = "Video", name: str = ""
    ) -> str:
        body: dict[str, Any] = {"GroupId": group_id, "URL": url, "AssetType": asset_type}
        if name:
            body["Name"] = name
        resp = self._call("CreateAsset", body)
        result = resp.get("Result", resp)
        return result.get("Id") or result.get("AssetId") or ""

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        resp = self._call("GetAsset", {"Id": asset_id})
        return resp.get("Result", resp)

    def list_asset_groups(self, group_type: str = "AIGC") -> list[dict[str, Any]]:
        resp = self._call("ListAssetGroups", {
            "Filter": {"GroupType": group_type},
            "PageNumber": 1, "PageSize": 100,
        })
        result = resp.get("Result", resp)
        return result.get("Items", [])

    def wait_asset_active(
        self, asset_id: str, *, interval: float = 5, timeout: float = 300
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            info = self.get_asset(asset_id)
            status = info.get("Status", "")
            if status == "Active":
                return info
            if status == "Failed":
                err = info.get("Error", {})
                msg = err.get("Message", "") if isinstance(err, dict) else str(err)
                raise RuntimeError(f"Asset {asset_id} failed: {msg}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Asset {asset_id} still {status} after {timeout}s")
            time.sleep(interval)

    # ── volcengine v4 signature ─────────────────────────────────

    def _call(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%dT%H%M%SZ")
        date_short = now.strftime("%Y%m%d")

        body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
        body_hash = hashlib.sha256(body_bytes).hexdigest()

        query = f"Action={action}&Version={self.VERSION}"
        path = "/"

        headers = {
            "Host": self.HOST,
            "Content-Type": "application/json",
            "X-Date": date_str,
        }

        signed_headers = "content-type;host;x-date"
        canonical_headers = (
            f"content-type:application/json\n"
            f"host:{self.HOST}\n"
            f"x-date:{date_str}\n"
        )

        canonical_request = "\n".join([
            "POST",
            path,
            query,
            canonical_headers,
            signed_headers,
            body_hash,
        ])

        credential_scope = f"{date_short}/{self.region}/{self.SERVICE}/request"
        string_to_sign = "\n".join([
            "HMAC-SHA256",
            date_str,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        k_date = self._hmac(date_short.encode(), self.sk.encode())
        k_region = self._hmac(self.region.encode(), k_date)
        k_service = self._hmac(self.SERVICE.encode(), k_region)
        k_signing = self._hmac(b"request", k_service)
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

        headers["Authorization"] = (
            f"HMAC-SHA256 Credential={self.ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        url = f"https://{self.HOST}/?{query}"
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, content=body_bytes, headers=headers)

        data = resp.json()
        meta = data.get("ResponseMetadata", {})
        error = meta.get("Error")
        if error:
            raise RuntimeError(f"Assets API error [{error.get('Code')}]: {error.get('Message')}")
        return data

    @staticmethod
    def _hmac(data: bytes, key: bytes) -> bytes:
        return hmac.new(key, data, hashlib.sha256).digest()

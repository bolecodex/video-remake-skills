"""Typed exceptions and stable exit codes."""

from __future__ import annotations

from dataclasses import dataclass


class WeiboError(Exception):
    code = "E_INTERNAL"
    exit_code = 1

    def __init__(self, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id


class ConfigError(WeiboError):
    code = "E_CONFIG"
    exit_code = 10


class AuthError(WeiboError):
    code = "E_AUTH"
    exit_code = 11


class RequestError(WeiboError):
    code = "E_REQUEST"
    exit_code = 12


class ServerError(WeiboError):
    code = "E_SERVER"
    exit_code = 13


class TimeoutError(WeiboError):
    code = "E_TIMEOUT"
    exit_code = 14


class NetworkError(WeiboError):
    code = "E_NETWORK"
    exit_code = 15


class FFmpegError(WeiboError):
    code = "E_FFMPEG"
    exit_code = 20


class ManifestError(WeiboError):
    code = "E_MANIFEST"
    exit_code = 21


class UploadError(WeiboError):
    code = "E_UPLOAD"
    exit_code = 22


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    request_id: str | None = None

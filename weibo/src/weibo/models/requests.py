"""Request payload models for Seedance API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VideoGenerateRequest(BaseModel):
    model: str
    prompt: str
    ratio: str = "9:16"
    duration: int = 15
    images: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)
    first_frame_url: str | None = None

    def to_api_payload(self) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        text_prompt = self.prompt.strip()
        if text_prompt:
            content.append({"type": "text", "text": text_prompt})

        for vid in self.video_urls:
            content.append(
                {
                    "type": "video_url",
                    "video_url": {"url": vid},
                    "role": "reference_video",
                }
            )

        if self.first_frame_url:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self.first_frame_url},
                }
            )
        else:
            for img in self.images:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": img},
                    }
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "content": content,
            "ratio": self.ratio,
            "duration": self.duration,
            "watermark": False,
        }
        return payload

"""Utility helpers: FFmpeg wrappers, image encoding, HTTP download."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import httpx

from weibo.errors import FFmpegError


def _run_ffmpeg(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        raise FFmpegError("ffmpeg not found. Install FFmpeg and ensure it is on PATH.")
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"FFmpeg timed out after {timeout}s: {' '.join(args[:6])}")
    if result.returncode != 0:
        stderr = result.stderr.strip()[-500:] if result.stderr else "(no stderr)"
        raise FFmpegError(f"FFmpeg exited {result.returncode}: {stderr}")
    return result


def get_video_ratio(video_path: Path) -> str:
    """Detect the aspect ratio of a video and return a Seedance-compatible ratio string."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "16:9"

    try:
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
    except (json.JSONDecodeError, KeyError, IndexError, ValueError):
        return "16:9"

    ratio = w / h
    if ratio < 0.6:
        return "9:16"
    elif ratio < 0.85:
        return "3:4"
    elif ratio < 1.15:
        return "1:1"
    elif ratio < 1.5:
        return "4:3"
    else:
        return "16:9"


def get_video_duration(video_path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise FFmpegError("ffprobe not found. Install FFmpeg and ensure it is on PATH.")
    except subprocess.TimeoutExpired:
        raise FFmpegError("ffprobe timed out.")

    try:
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise FFmpegError(f"Cannot parse video duration: {exc}") from exc


def split_video(
    video_path: Path,
    output_dir: Path,
    segment_seconds: int = 15,
) -> list[Path]:
    """Split video into segments of at most `segment_seconds` each.

    Uses per-segment ``-ss / -t`` with re-encoding for frame-accurate
    boundaries (the segment muxer with stream-copy cuts at keyframes only,
    which often produces segments that exceed the Seedance 15-second limit).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = get_video_duration(video_path)

    segments: list[Path] = []
    idx = 0
    start = 0.0
    while start < duration:
        out_file = output_dir / f"{idx:03d}.mp4"
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", str(video_path),
            "-t", str(segment_seconds),
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac",
            str(out_file),
        ], timeout=600)
        if out_file.exists() and out_file.stat().st_size > 0:
            segments.append(out_file)
        start += segment_seconds
        idx += 1

    if not segments:
        raise FFmpegError(f"No segments produced from {video_path}")
    return segments


def extract_first_frame(video_path: Path, output_path: Path) -> Path:
    """Extract the first frame of a video as JPEG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "1",
        str(output_path),
    ])
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FFmpegError(f"Failed to extract frame from {video_path}")
    return output_path


def concat_videos(video_paths: list[Path], output_path: Path) -> Path:
    """Concatenate videos using FFmpeg concat demuxer with re-encoding."""
    if not video_paths:
        raise FFmpegError("No videos to concatenate.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / "_concat_list.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for vp in video_paths:
            f.write(f"file '{vp.resolve()}'\n")
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264",
        "-crf", "18",
        "-c:a", "aac",
        str(output_path),
    ], timeout=600)
    list_file.unlink(missing_ok=True)
    if not output_path.exists():
        raise FFmpegError("Concat produced no output file.")
    return output_path


def mux_audio(
    video_path: Path,
    audio_source: Path,
    output_path: Path,
) -> Path:
    """Replace audio track of video_path with audio from audio_source."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_source),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ])
    return output_path


def extract_multi_frames(video_path: Path, output_dir: Path, prefix: str = "") -> list[Path]:
    """Extract first, middle, and last frames from a video."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix or video_path.stem
    results: list[Path] = []

    first_frame = output_dir / f"{stem}_first.jpg"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vframes", "1", "-q:v", "1",
        str(first_frame),
    ])
    if first_frame.exists() and first_frame.stat().st_size > 0:
        results.append(first_frame)

    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_frames",
                "-show_entries", "stream=nb_read_frames",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        total_frames = int(probe.stdout.strip()) if probe.stdout.strip().isdigit() else 300
    except (subprocess.TimeoutExpired, ValueError):
        total_frames = 300

    mid_n = total_frames // 2
    mid_frame = output_dir / f"{stem}_mid.jpg"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"select=eq(n\\,{mid_n})",
        "-vframes", "1", "-q:v", "1",
        str(mid_frame),
    ])
    if mid_frame.exists() and mid_frame.stat().st_size > 0:
        results.append(mid_frame)

    last_frame = output_dir / f"{stem}_last.jpg"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-sseof", "-1",
        "-i", str(video_path),
        "-update", "1", "-q:v", "1",
        str(last_frame),
    ])
    if last_frame.exists() and last_frame.stat().st_size > 0:
        results.append(last_frame)

    return results


def encode_image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "png"
    if suffix == "jpg":
        suffix = "jpeg"
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/{suffix};base64,{b64}"


def download_file(url: str, output_path: Path) -> Path:
    with httpx.Client(timeout=300) as client:
        resp = client.get(url)
        resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)
    return output_path

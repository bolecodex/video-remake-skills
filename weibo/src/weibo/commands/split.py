"""weibo split — split a video into segments and extract reference frames."""

from __future__ import annotations

from pathlib import Path

import typer

from weibo.config import PRESET_PROMPTS, AppConfig
from weibo.manifest import Manifest, SegmentEntry
from weibo.upload import TOSConfig, upload_file
from weibo.utils import extract_first_frame, get_video_duration, split_video


def register_split(app: typer.Typer) -> None:
    @app.command("split")
    def split_cmd(
        ctx: typer.Context,
        video: Path = typer.Argument(..., help="输入视频路径。"),
        output: Path = typer.Option(
            ..., "-o", "--output", help="任务输出目录。"
        ),
        segment_seconds: int = typer.Option(
            15, "--segment-seconds", "-s", help="每段最大秒数（默认 15，Seedance 上限）。"
        ),
        preset: str = typer.Option(
            "h2v", "--preset", "-p", help="预设模式：h2v / style_transfer / character_swap / viral_replica"
        ),
        prompt: str = typer.Option(
            "", "--prompt", help="附加提示词（追加在预设之后）。"
        ),
        no_upload: bool = typer.Option(
            False, "--no-upload", help="跳过 TOS 上传（仅本地分割）。"
        ),
    ) -> None:
        """将视频按固定时长分割，提取每段首帧，上传 TOS，生成 manifest.json。"""
        config: AppConfig = ctx.obj

        if not video.exists():
            typer.echo(f"Error: 输入视频不存在: {video}", err=True)
            raise typer.Exit(1)

        if preset not in PRESET_PROMPTS:
            typer.echo(
                f"Error: 未知预设 '{preset}'，可选：{', '.join(PRESET_PROMPTS)}",
                err=True,
            )
            raise typer.Exit(1)

        output.mkdir(parents=True, exist_ok=True)
        segments_dir = output / "segments"
        frames_dir = output / "frames"
        (output / "remade").mkdir(parents=True, exist_ok=True)
        (output / "prompts").mkdir(parents=True, exist_ok=True)

        duration = get_video_duration(video)
        typer.echo(f"源视频时长: {duration:.1f}s，分段: {segment_seconds}s")

        segment_files = split_video(video, segments_dir, segment_seconds)
        typer.echo(f"已分割为 {len(segment_files)} 个片段")

        should_upload = not no_upload and config.tos_available
        tos_cfg: TOSConfig | None = None
        if should_upload:
            tos_cfg = TOSConfig(
                access_key=config.tos_access_key,
                secret_key=config.tos_secret_key,
                bucket=config.tos_bucket,
                endpoint=config.tos_endpoint,
                region=config.tos_region,
            )
            typer.echo("上传片段到 TOS...")
        elif not no_upload and not config.tos_available:
            typer.echo("Warning: TOS 未配置，跳过上传。remake 将使用 image 模式。", err=True)

        entries: list[SegmentEntry] = []
        for i, seg in enumerate(segment_files):
            frame_path = frames_dir / f"{i:03d}.jpg"
            extract_first_frame(seg, frame_path)

            segment_url: str | None = None
            if should_upload and tos_cfg:
                try:
                    segment_url = upload_file(seg, prefix="weibo/segments/", tos_cfg=tos_cfg)
                    typer.echo(f"  [{i:03d}] 已上传: {segment_url}")
                except Exception as exc:
                    typer.echo(f"  [{i:03d}] 上传失败: {exc}", err=True)

            entries.append(
                SegmentEntry(
                    index=i,
                    source_path=str(seg.relative_to(output)),
                    frame_path=str(frame_path.relative_to(output)),
                    segment_url=segment_url,
                )
            )
        typer.echo(f"已提取 {len(entries)} 个参考帧")

        full_prompt = PRESET_PROMPTS[preset]
        if prompt:
            full_prompt = f"{full_prompt}\n{prompt}"

        manifest = Manifest(
            source=str(video.resolve()),
            preset=preset,
            prompt=full_prompt,
            segment_seconds=segment_seconds,
            segments=entries,
        )
        manifest_path = output / "manifest.json"
        manifest.save(manifest_path)
        typer.echo(f"Manifest 已保存: {manifest_path}")
        typer.echo("下一步: weibo remake " + str(manifest_path))

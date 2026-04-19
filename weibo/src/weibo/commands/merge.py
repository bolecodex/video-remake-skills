"""weibo merge — concatenate remade segments into the final video."""

from __future__ import annotations

from pathlib import Path

import typer

from weibo.config import AppConfig
from weibo.manifest import Manifest
from weibo.utils import concat_videos, mux_audio


def register_merge(app: typer.Typer) -> None:
    @app.command("merge")
    def merge_cmd(
        ctx: typer.Context,
        manifest_path: Path = typer.Argument(..., help="manifest.json 路径。"),
        output: Path = typer.Option(
            None, "-o", "--output", help="输出文件路径（默认: 任务目录/final.mp4）。"
        ),
        keep_audio: bool = typer.Option(
            False, "--keep-audio", help="从源视频提取音轨合入成片。"
        ),
    ) -> None:
        """将所有成功重制的片段按顺序合并。"""
        config: AppConfig = ctx.obj
        manifest = Manifest.load(manifest_path)
        job_dir = manifest_path.parent

        succeeded = manifest.succeeded_segments()
        if not succeeded:
            typer.echo("Error: 没有成功重制的片段可合并。", err=True)
            raise typer.Exit(1)

        succeeded.sort(key=lambda s: s.index)
        video_paths = []
        for seg in succeeded:
            rp = job_dir / seg.remade_path
            if not rp.exists():
                typer.echo(f"Warning: 片段 {seg.index:03d} 文件缺失: {rp}", err=True)
                continue
            video_paths.append(rp)

        if not video_paths:
            typer.echo("Error: 所有重制文件均缺失。", err=True)
            raise typer.Exit(1)

        total = len(manifest.segments)
        typer.echo(f"合并 {len(video_paths)}/{total} 个片段")

        out_path = output or (job_dir / "final.mp4")
        concat_videos(video_paths, out_path)
        typer.echo(f"拼接完成: {out_path}")

        if keep_audio:
            source_video = Path(manifest.source)
            if source_video.exists():
                muxed = out_path.with_stem(out_path.stem + "_audio")
                mux_audio(out_path, source_video, muxed)
                muxed.rename(out_path)
                typer.echo("已合入源视频音轨")
            else:
                typer.echo(f"Warning: 源视频不存在，跳过音轨合入: {source_video}", err=True)

        typer.echo(f"成片: {out_path}")

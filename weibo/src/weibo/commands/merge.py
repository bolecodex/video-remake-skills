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
        """将所有成功重制的片段按顺序合并。失败片段用源片段填补以保持时长完整。"""
        config: AppConfig = ctx.obj
        manifest = Manifest.load(manifest_path)
        job_dir = manifest_path.parent

        all_sorted = sorted(manifest.segments, key=lambda s: s.index)
        video_paths: list[Path] = []
        fallback_count = 0

        for seg in all_sorted:
            if seg.status == "succeeded" and seg.remade_path:
                rp = job_dir / seg.remade_path
                if rp.exists():
                    video_paths.append(rp)
                    continue
                typer.echo(f"Warning: 片段 {seg.index:03d} 重制文件缺失: {rp}", err=True)

            sp = job_dir / seg.source_path
            if sp.exists():
                video_paths.append(sp)
                fallback_count += 1
                typer.echo(
                    f"Warning: 片段 {seg.index:03d} 使用源片段填补（{seg.status}）",
                    err=True,
                )
            else:
                typer.echo(f"Warning: 片段 {seg.index:03d} 源片段也缺失，跳过", err=True)

        if not video_paths:
            typer.echo("Error: 没有可用的片段可合并。", err=True)
            raise typer.Exit(1)

        total = len(manifest.segments)
        typer.echo(f"合并 {len(video_paths)}/{total} 个片段")
        if fallback_count:
            typer.echo(
                f"WARNING: {fallback_count} 个片段使用源视频填补（未重制成功）",
                err=True,
            )

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

"""weibo query — check task status or manifest summary."""

from __future__ import annotations

from pathlib import Path

import typer

from weibo.client.ark_base import ArkClient
from weibo.client.polling import PollConfig, normalize_status, poll_task
from weibo.client.seedance import SeedanceClient
from weibo.config import AppConfig
from weibo.manifest import Manifest
from weibo.utils import download_file


def _build_seedance_client(config: AppConfig) -> SeedanceClient:
    return SeedanceClient(
        client=ArkClient(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout_s=config.request_timeout_s,
        ),
        submit_endpoint=config.video_submit_endpoint,
        status_endpoint_template=config.video_status_endpoint_template,
    )


def _show_manifest_summary(manifest_path: Path) -> None:
    m = Manifest.load(manifest_path)
    total = len(m.segments)
    pending = sum(1 for s in m.segments if s.status == "pending")
    succeeded = sum(1 for s in m.segments if s.status == "succeeded")
    failed = sum(1 for s in m.segments if s.status == "failed")

    typer.echo(f"源视频: {m.source}")
    typer.echo(f"预设: {m.preset}")
    typer.echo(f"分段: {total} 段 × {m.segment_seconds}s")
    typer.echo(f"状态: {succeeded} 成功 / {pending} 待处理 / {failed} 失败")
    typer.echo("")

    for seg in m.segments:
        status_icon = {"succeeded": "[OK]", "failed": "[FAIL]", "pending": "[..]"}.get(
            seg.status, "[??]"
        )
        tid = seg.task_id or "-"
        typer.echo(f"  {status_icon} {seg.index:03d}  task={tid}  {seg.status}")


def register_query(app: typer.Typer) -> None:
    @app.command("query")
    def query_cmd(
        ctx: typer.Context,
        task_id: str = typer.Option("", "--task-id", "-t", help="Seedance 任务 ID。"),
        manifest: Path = typer.Option(None, "--manifest", "-m", help="manifest.json 路径（显示汇总）。"),
        wait: bool = typer.Option(False, "--wait", "-w", help="等待任务完成。"),
        output: Path = typer.Option(None, "--output", "-o", help="等待完成后保存视频路径。"),
    ) -> None:
        """查询单个任务状态，或显示 manifest 中所有段的状态汇总。"""
        config: AppConfig = ctx.obj

        if manifest:
            _show_manifest_summary(manifest)
            return

        if not task_id:
            typer.echo("Error: 请提供 --task-id 或 --manifest。", err=True)
            raise typer.Exit(1)

        sc = _build_seedance_client(config)

        if not wait:
            result = sc.status(task_id)
            normalized = normalize_status(result.status)
            typer.echo(f"任务ID: {task_id}")
            typer.echo(f"状态: {result.status} ({normalized})")
            if result.file_url:
                typer.echo(f"视频URL: {result.file_url}")
            if result.fail_reason:
                typer.echo(f"失败原因: {result.fail_reason}")
            return

        typer.echo(f"等待任务 {task_id} 完成...")
        poll_cfg = PollConfig(
            interval_s=config.poll_interval_s,
            max_wait_s=config.poll_max_wait_s,
        )

        def _on_update(resp, normalized):
            typer.echo(f"  状态: {resp.status} → {normalized}")

        result = poll_task(
            fetcher=sc.status,
            task_id=task_id,
            config=poll_cfg,
            on_update=_on_update,
        )

        normalized = normalize_status(result.status)
        if normalized == "succeeded" and result.file_url:
            typer.echo(f"任务完成: {result.file_url}")
            if output:
                download_file(result.file_url, output)
                typer.echo(f"已保存: {output}")
        elif normalized == "failed":
            typer.echo(f"任务失败: {result.fail_reason or result.status}", err=True)
            raise typer.Exit(1)

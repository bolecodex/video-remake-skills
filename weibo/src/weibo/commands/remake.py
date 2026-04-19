"""weibo remake — re-generate each segment via Seedance 2.0."""

from __future__ import annotations

from pathlib import Path

import typer

from weibo.client.ark_base import ArkClient
from weibo.client.polling import PollConfig, normalize_status, poll_task
from weibo.client.seedance import SeedanceClient
from weibo.config import PRESET_RATIOS, AppConfig
from weibo.manifest import Manifest
from weibo.models.requests import VideoGenerateRequest
from weibo.utils import download_file, encode_image_to_data_url, get_video_ratio


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


def _segment_prompt(manifest: Manifest, index: int, job_dir: Path) -> str:
    override_file = job_dir / "prompts" / f"{index:03d}.txt"
    if override_file.exists():
        custom = override_file.read_text(encoding="utf-8").strip()
        if custom:
            return custom
    return manifest.prompt


def register_remake(app: typer.Typer) -> None:
    @app.command("remake")
    def remake_cmd(
        ctx: typer.Context,
        manifest_path: Path = typer.Argument(..., help="manifest.json 路径。"),
        prompt: str = typer.Option(
            "", "--prompt", help="覆盖所有段的提示词（优先级低于 prompts/NNN.txt）。"
        ),
        model: str = typer.Option("", "--model", help="临时覆盖视频模型/端点 ID。"),
        ratio: str = typer.Option("", "--ratio", help="临时覆盖输出比例。"),
        duration: int = typer.Option(0, "--duration", help="临时覆盖视频时长（秒）。"),
        use_image: bool = typer.Option(
            False, "--use-image", help="强制使用首帧图片参考（而非视频参考）。"
        ),
    ) -> None:
        """读取 manifest，对每个 pending 段提交 Seedance 2.0 并轮询下载。"""
        config: AppConfig = ctx.obj
        manifest = Manifest.load(manifest_path)
        job_dir = manifest_path.parent

        pending = [s for s in manifest.segments if s.status in ("pending", "failed")]
        if not pending:
            typer.echo("没有待处理的片段（所有段已完成）。")
            raise typer.Exit(0)

        preset_ratio = PRESET_RATIOS.get(manifest.preset)
        if not preset_ratio:
            source = Path(manifest.source)
            preset_ratio = get_video_ratio(source) if source.exists() else config.video_ratio
        target_ratio = ratio or preset_ratio
        target_model = model or config.video_model
        target_duration = duration or config.video_duration

        sc = _build_seedance_client(config)
        poll_cfg = PollConfig(
            interval_s=config.poll_interval_s,
            max_wait_s=config.poll_max_wait_s,
        )

        has_video_urls = any(s.segment_url for s in pending)
        mode = "image" if (use_image or not has_video_urls) else "video"
        typer.echo(f"开始重制 {len(pending)} 个片段 (model={target_model}, ratio={target_ratio}, ref={mode})")

        for seg in pending:
            idx = seg.index
            typer.echo(f"\n── 片段 {idx:03d} ──")

            if seg.task_id:
                try:
                    existing = sc.status(seg.task_id)
                    existing_norm = normalize_status(existing.status)
                    if existing_norm == "succeeded" and existing.file_url:
                        typer.echo(f"  已有 task 已完成: {seg.task_id}")
                        remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
                        download_file(existing.file_url, remade_path)
                        seg.remade_path = str(remade_path.relative_to(job_dir))
                        seg.status = "succeeded"
                        manifest.save(manifest_path)
                        typer.echo(f"  [OK] 已保存: {seg.remade_path}")
                        continue
                    if existing_norm == "running":
                        typer.echo(f"  恢复轮询已有 task: {seg.task_id}")
                        seg.status = "pending"
                        manifest.save(manifest_path)
                        # fall through to polling below
                        def _on_update(resp, normalized):
                            typer.echo(f"  轮询: {resp.status} → {normalized}")
                        try:
                            result = poll_task(
                                fetcher=sc.status,
                                task_id=seg.task_id,
                                config=poll_cfg,
                                on_update=_on_update,
                            )
                        except Exception as exc:
                            typer.echo(f"  [FAIL] 轮询失败: {exc}", err=True)
                            seg.status = "failed"
                            manifest.save(manifest_path)
                            continue
                        normalized = normalize_status(result.status)
                        if normalized == "succeeded" and result.file_url:
                            remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
                            download_file(result.file_url, remade_path)
                            seg.remade_path = str(remade_path.relative_to(job_dir))
                            seg.status = "succeeded"
                            manifest.save(manifest_path)
                            typer.echo(f"  [OK] 已保存: {seg.remade_path}")
                        else:
                            reason = result.fail_reason or result.status
                            typer.echo(f"  [FAIL] 生成失败: {reason}", err=True)
                            seg.status = "failed"
                            manifest.save(manifest_path)
                        continue
                except Exception:
                    pass
                seg.task_id = None

            seg_prompt = prompt if prompt else _segment_prompt(manifest, idx, job_dir)

            if mode == "video" and seg.segment_url:
                req = VideoGenerateRequest(
                    model=target_model,
                    prompt=seg_prompt,
                    ratio=target_ratio,
                    duration=target_duration,
                    video_urls=[seg.segment_url],
                )
                typer.echo(f"  参考视频: {seg.segment_url}")
            else:
                frame_path = job_dir / seg.frame_path
                if not frame_path.exists():
                    typer.echo(f"  [SKIP] 参考帧不存在: {frame_path}", err=True)
                    seg.status = "failed"
                    manifest.save(manifest_path)
                    continue
                image_data_url = encode_image_to_data_url(frame_path)
                req = VideoGenerateRequest(
                    model=target_model,
                    prompt=seg_prompt,
                    ratio=target_ratio,
                    duration=target_duration,
                    images=[image_data_url],
                )

            try:
                submitted = sc.submit(req)
            except Exception as exc:
                typer.echo(f"  [FAIL] 提交失败: {exc}", err=True)
                seg.status = "failed"
                manifest.save(manifest_path)
                continue

            seg.task_id = submitted.task_id
            typer.echo(f"  已提交 task_id={submitted.task_id}")
            manifest.save(manifest_path)

            def _on_update(resp, normalized):
                typer.echo(f"  轮询: {resp.status} → {normalized}")

            try:
                result = poll_task(
                    fetcher=sc.status,
                    task_id=submitted.task_id,
                    config=poll_cfg,
                    on_update=_on_update,
                )
            except Exception as exc:
                typer.echo(f"  [FAIL] 轮询失败: {exc}", err=True)
                seg.status = "failed"
                manifest.save(manifest_path)
                continue

            normalized = normalize_status(result.status)
            if normalized != "succeeded" or not result.file_url:
                reason = result.fail_reason or result.status
                typer.echo(f"  [FAIL] 生成失败: {reason}", err=True)
                seg.status = "failed"
                manifest.save(manifest_path)
                continue

            remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
            try:
                download_file(result.file_url, remade_path)
            except Exception as exc:
                typer.echo(f"  [FAIL] 下载失败: {exc}", err=True)
                seg.status = "failed"
                manifest.save(manifest_path)
                continue

            seg.remade_path = str(remade_path.relative_to(job_dir))
            seg.status = "succeeded"
            manifest.save(manifest_path)
            typer.echo(f"  [OK] 已保存: {seg.remade_path}")

        succeeded = len(manifest.succeeded_segments())
        total = len(manifest.segments)
        typer.echo(f"\n重制完成: {succeeded}/{total} 成功")
        if succeeded > 0:
            typer.echo(f"下一步: weibo merge {manifest_path}")

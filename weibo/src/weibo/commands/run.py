"""weibo run — one-shot pipeline: split → upload → remake → merge."""

from __future__ import annotations

from pathlib import Path

import typer

from weibo.assets import AssetsClient
from weibo.client.ark_base import ArkClient
from weibo.client.polling import PollConfig, normalize_status, poll_task
from weibo.client.seedance import SeedanceClient
from weibo.config import PRESET_PROMPTS, PRESET_RATIOS, AppConfig
from weibo.manifest import Manifest, SegmentEntry
from weibo.models.requests import VideoGenerateRequest
from weibo.upload import TOSConfig, upload_file
from weibo.utils import (
    concat_videos,
    download_file,
    encode_image_to_data_url,
    extract_first_frame,
    get_video_duration,
    get_video_ratio,
    mux_audio,
    sketch_frame,
    split_video,
)


def register_run(app: typer.Typer) -> None:
    @app.command("run")
    def run_cmd(
        ctx: typer.Context,
        video: Path = typer.Argument(..., help="输入视频路径。"),
        output: Path = typer.Option(
            ..., "-o", "--output", help="任务输出目录。"
        ),
        segment_seconds: int = typer.Option(
            15, "--segment-seconds", "-s", help="每段最大秒数（默认 15）。"
        ),
        preset: str = typer.Option(
            "h2v", "--preset", "-p", help="预设模式：h2v / v2h / style_transfer / character_swap / viral_replica"
        ),
        prompt: str = typer.Option(
            "", "--prompt", help="附加提示词。"
        ),
        keep_audio: bool = typer.Option(
            True, "--keep-audio/--no-keep-audio", help="从源视频提取音轨合入成片（默认开启）。"
        ),
        no_upload: bool = typer.Option(
            False, "--no-upload", help="跳过 TOS 上传，使用首帧图片参考。"
        ),
        auto_asset: bool = typer.Option(
            True, "--auto-asset/--no-auto-asset",
            help="失败片段自动注册 Asset 后重试（默认开启，需 TOS 配置）。",
        ),
    ) -> None:
        """一键执行完整流水线：分割 → 上传 → Seedance 重制 → 合并。"""
        config: AppConfig = ctx.obj

        if not video.exists():
            typer.echo(f"Error: 输入视频不存在: {video}", err=True)
            raise typer.Exit(1)
        if preset not in PRESET_PROMPTS:
            typer.echo(f"Error: 未知预设 '{preset}'", err=True)
            raise typer.Exit(1)

        manifest_path = output / "manifest.json"

        # --- Step 1: Split + Upload ---
        typer.echo("=" * 50)
        typer.echo(" Step 1/3: 分割视频 + 上传 TOS")
        typer.echo("=" * 50)

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

            entries.append(SegmentEntry(
                index=i,
                source_path=str(seg.relative_to(output)),
                frame_path=str(frame_path.relative_to(output)),
                segment_url=segment_url,
            ))

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
        manifest.save(manifest_path)
        typer.echo(f"已提取 {len(entries)} 个参考帧")

        # --- Step 2: Remake ---
        typer.echo("")
        typer.echo("=" * 50)
        typer.echo(" Step 2/3: Seedance 2.0 重制")
        typer.echo("=" * 50)

        target_ratio = PRESET_RATIOS.get(preset) or get_video_ratio(video)
        sc = SeedanceClient(
            client=ArkClient(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout_s=config.request_timeout_s,
            ),
            submit_endpoint=config.video_submit_endpoint,
            status_endpoint_template=config.video_status_endpoint_template,
        )
        poll_cfg = PollConfig(
            interval_s=config.poll_interval_s,
            max_wait_s=config.poll_max_wait_s,
        )

        job_dir = output
        for seg_entry in manifest.segments:
            idx = seg_entry.index
            typer.echo(f"\n── 片段 {idx:03d} ──")

            if seg_entry.segment_url:
                req = VideoGenerateRequest(
                    model=config.video_model,
                    prompt=full_prompt,
                    ratio=target_ratio,
                    duration=config.video_duration,
                    video_urls=[seg_entry.segment_url],
                )
                typer.echo(f"  参考视频: {seg_entry.segment_url}")
            else:
                frame_path = job_dir / seg_entry.frame_path
                image_data_url = encode_image_to_data_url(frame_path)
                req = VideoGenerateRequest(
                    model=config.video_model,
                    prompt=full_prompt,
                    ratio=target_ratio,
                    duration=config.video_duration,
                    images=[image_data_url],
                )

            try:
                submitted = sc.submit(req)
                seg_entry.task_id = submitted.task_id
                typer.echo(f"  已提交 task_id={submitted.task_id}")
                manifest.save(manifest_path)

                result = poll_task(
                    fetcher=sc.status,
                    task_id=submitted.task_id,
                    config=poll_cfg,
                    on_update=lambda resp, n: typer.echo(f"  轮询: {resp.status} → {n}"),
                )
                normalized = normalize_status(result.status)
                if normalized == "succeeded" and result.file_url:
                    remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
                    download_file(result.file_url, remade_path)
                    seg_entry.remade_path = str(remade_path.relative_to(job_dir))
                    seg_entry.status = "succeeded"
                    typer.echo(f"  [OK] {seg_entry.remade_path}")
                else:
                    fail_msg = result.fail_reason or result.status
                    seg_entry.status = "failed"
                    typer.echo(f"  [FAIL] {fail_msg}", err=True)
            except Exception as exc:
                fail_msg = str(exc)
                seg_entry.status = "failed"
                typer.echo(f"  [FAIL] {fail_msg}", err=True)

            if seg_entry.status == "failed" and "real person" in fail_msg.lower():
                typer.echo(f"  真人检测拦截，改用线稿参考帧重试...")
                frame_path = job_dir / seg_entry.frame_path
                sketch_path = sketch_frame(frame_path)
                sketch_data_url = encode_image_to_data_url(sketch_path)
                sketch_req = VideoGenerateRequest(
                    model=config.video_model,
                    prompt=full_prompt,
                    ratio=target_ratio,
                    duration=config.video_duration,
                    images=[sketch_data_url],
                )
                try:
                    submitted = sc.submit(sketch_req)
                    seg_entry.task_id = submitted.task_id
                    typer.echo(f"  已提交 (线稿) task_id={submitted.task_id}")
                    manifest.save(manifest_path)
                    result = poll_task(
                        fetcher=sc.status,
                        task_id=submitted.task_id,
                        config=poll_cfg,
                        on_update=lambda resp, n: typer.echo(f"  轮询: {resp.status} → {n}"),
                    )
                    normalized = normalize_status(result.status)
                    if normalized == "succeeded" and result.file_url:
                        remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
                        download_file(result.file_url, remade_path)
                        seg_entry.remade_path = str(remade_path.relative_to(job_dir))
                        seg_entry.status = "succeeded"
                        typer.echo(f"  [OK] (线稿) {seg_entry.remade_path}")
                    else:
                        seg_entry.status = "failed"
                        typer.echo(f"  [FAIL] (线稿) {result.fail_reason or result.status}", err=True)
                except Exception as exc2:
                    seg_entry.status = "failed"
                    typer.echo(f"  [FAIL] (线稿) {exc2}", err=True)

            manifest.save(manifest_path)

        succeeded_segs = manifest.succeeded_segments()
        failed_segs = [s for s in manifest.segments if s.status == "failed"]
        typer.echo(f"\n重制完成: {len(succeeded_segs)}/{len(manifest.segments)} 成功")

        if failed_segs and auto_asset and config.tos_available:
            typer.echo("")
            typer.echo("=" * 50)
            typer.echo(" 自动 Asset 注册 + 重试失败片段")
            typer.echo("=" * 50)

            try:
                ac = AssetsClient(config.tos_access_key, config.tos_secret_key, config.tos_region)
                group_name = f"weibo-auto-{output.name}"
                groups = ac.list_asset_groups()
                group_id = ""
                for g in groups:
                    if g.get("Name") == group_name:
                        group_id = g["Id"]
                        break
                if not group_id:
                    group_id = ac.create_asset_group(group_name)
                    typer.echo(f"  已创建 AssetGroup: {group_id}")

                registered_any = False
                for seg_entry in failed_segs:
                    if not seg_entry.segment_url or seg_entry.segment_url.startswith("asset://"):
                        continue
                    try:
                        asset_id = ac.create_asset(group_id, seg_entry.segment_url, asset_type="Video")
                        typer.echo(f"  [{seg_entry.index:03d}] 注册 Asset: {asset_id}")
                        ac.wait_asset_active(asset_id, interval=5, timeout=300)
                        seg_entry.segment_url = f"asset://{asset_id}"
                        seg_entry.status = "pending"
                        seg_entry.task_id = None
                        registered_any = True
                        typer.echo(f"  [{seg_entry.index:03d}] Asset 就绪")
                    except Exception as exc:
                        typer.echo(f"  [{seg_entry.index:03d}] Asset 注册失败: {exc}", err=True)
                manifest.save(manifest_path)

                if registered_any:
                    import time as _time
                    typer.echo("  等待 30s 让 Asset 在 Seedance 侧生效...")
                    _time.sleep(30)
            except Exception as exc:
                typer.echo(f"  Asset 注册异常: {exc}", err=True)

            retry_segs = [s for s in manifest.segments if s.status == "pending"]
            for seg_entry in retry_segs:
                idx = seg_entry.index
                typer.echo(f"\n── 重试片段 {idx:03d} ──")

                if seg_entry.segment_url:
                    req = VideoGenerateRequest(
                        model=config.video_model,
                        prompt=full_prompt,
                        ratio=target_ratio,
                        duration=config.video_duration,
                        video_urls=[seg_entry.segment_url],
                    )
                else:
                    frame_path = job_dir / seg_entry.frame_path
                    image_data_url = encode_image_to_data_url(frame_path)
                    req = VideoGenerateRequest(
                        model=config.video_model,
                        prompt=full_prompt,
                        ratio=target_ratio,
                        duration=config.video_duration,
                        images=[image_data_url],
                    )

                try:
                    submitted = sc.submit(req)
                    seg_entry.task_id = submitted.task_id
                    typer.echo(f"  已提交 task_id={submitted.task_id}")
                    manifest.save(manifest_path)
                    result = poll_task(
                        fetcher=sc.status,
                        task_id=submitted.task_id,
                        config=poll_cfg,
                        on_update=lambda resp, n: typer.echo(f"  轮询: {resp.status} → {n}"),
                    )
                    normalized = normalize_status(result.status)
                    if normalized == "succeeded" and result.file_url:
                        remade_path = job_dir / "remade" / f"{idx:03d}.mp4"
                        download_file(result.file_url, remade_path)
                        seg_entry.remade_path = str(remade_path.relative_to(job_dir))
                        seg_entry.status = "succeeded"
                        typer.echo(f"  [OK] {seg_entry.remade_path}")
                    else:
                        seg_entry.status = "failed"
                        typer.echo(f"  [FAIL] {result.fail_reason or result.status}", err=True)
                except Exception as exc:
                    seg_entry.status = "failed"
                    typer.echo(f"  [FAIL] {exc}", err=True)
                manifest.save(manifest_path)

            succeeded_segs = manifest.succeeded_segments()
            typer.echo(f"\n重试后: {len(succeeded_segs)}/{len(manifest.segments)} 成功")

        # --- Step 3: Merge ---
        if not succeeded_segs:
            typer.echo("没有成功片段，跳过合并。", err=True)
            return

        typer.echo("")
        typer.echo("=" * 50)
        typer.echo(" Step 3/3: 合并成片")
        typer.echo("=" * 50)

        succeeded_segs.sort(key=lambda s: s.index)
        video_paths = [job_dir / s.remade_path for s in succeeded_segs if (job_dir / s.remade_path).exists()]
        out_path = job_dir / "final.mp4"
        concat_videos(video_paths, out_path)
        typer.echo(f"拼接完成: {out_path}")

        if keep_audio and Path(manifest.source).exists():
            muxed = out_path.with_stem(out_path.stem + "_audio")
            mux_audio(out_path, Path(manifest.source), muxed)
            muxed.rename(out_path)
            typer.echo("已合入源视频音轨")

        typer.echo(f"成片: {out_path}")

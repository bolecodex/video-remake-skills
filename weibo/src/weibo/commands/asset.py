"""weibo asset — manage assets for real-person video bypass."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from weibo.assets import AssetsClient
from weibo.config import AppConfig
from weibo.manifest import Manifest


def _build_assets_client(config: AppConfig) -> AssetsClient:
    if not config.tos_access_key or not config.tos_secret_key:
        typer.echo("Error: Assets API 需要 VOLC_ACCESSKEY 和 VOLC_SECRETKEY。", err=True)
        raise typer.Exit(1)
    return AssetsClient(config.tos_access_key, config.tos_secret_key, config.tos_region)


def register_asset(app: typer.Typer) -> None:
    @app.command("asset-register")
    def asset_register_cmd(
        ctx: typer.Context,
        manifest_path: Path = typer.Argument(..., help="manifest.json 路径。"),
        group_name: str = typer.Option(
            "weibo-h2v", "--group-name", "-g", help="Asset Group 名称。"
        ),
    ) -> None:
        """将 manifest 中所有片段的 TOS URL 注册为 Asset（解决真人审核拦截）。"""
        config: AppConfig = ctx.obj
        ac = _build_assets_client(config)
        manifest = Manifest.load(manifest_path)

        groups = ac.list_asset_groups()
        group_id = ""
        for g in groups:
            if g.get("Name") == group_name:
                group_id = g["Id"]
                typer.echo(f"已有 AssetGroup: {group_id}")
                break

        if not group_id:
            group_id = ac.create_asset_group(group_name)
            typer.echo(f"已创建 AssetGroup: {group_id}")

        changed = False
        for seg in manifest.segments:
            if not seg.segment_url:
                typer.echo(f"  [{seg.index:03d}] 跳过：无 segment_url")
                continue

            if seg.segment_url.startswith("asset://"):
                typer.echo(f"  [{seg.index:03d}] 已是 Asset: {seg.segment_url}")
                continue

            typer.echo(f"  [{seg.index:03d}] 注册 Asset: {seg.segment_url}")
            try:
                asset_id = ac.create_asset(group_id, seg.segment_url, asset_type="Video")
                typer.echo(f"  [{seg.index:03d}] asset_id={asset_id}, 等待 Active...")
                ac.wait_asset_active(asset_id, interval=5, timeout=300)
                seg.segment_url = f"asset://{asset_id}"
                typer.echo(f"  [{seg.index:03d}] OK: {seg.segment_url}")
                changed = True
            except Exception as exc:
                typer.echo(f"  [{seg.index:03d}] FAIL: {exc}", err=True)

        if changed:
            seg_status_reset = [s for s in manifest.segments if s.status == "failed"]
            for s in seg_status_reset:
                s.status = "pending"
            manifest.save(manifest_path)
            typer.echo(f"\nManifest 已更新: {manifest_path}")
            typer.echo("下一步: weibo remake " + str(manifest_path))
        else:
            typer.echo("\n无需更新。")

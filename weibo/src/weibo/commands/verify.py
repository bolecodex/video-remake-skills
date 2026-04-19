"""weibo verify — generate an HTML comparison report for visual QA."""

from __future__ import annotations

import base64
import webbrowser
from datetime import datetime
from pathlib import Path

import typer

from weibo.config import AppConfig
from weibo.manifest import Manifest
from weibo.utils import extract_multi_frames


def _img_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _build_html(manifest: Manifest, job_dir: Path, frame_pairs: list[dict]) -> str:
    total = len(manifest.segments)
    succeeded = sum(1 for s in manifest.segments if s.status == "succeeded")
    failed = sum(1 for s in manifest.segments if s.status == "failed")
    pending = sum(1 for s in manifest.segments if s.status == "pending")

    segment_cards = []
    for fp in frame_pairs:
        src_imgs = ""
        for label, img_path in fp["source_frames"]:
            uri = _img_to_data_uri(img_path)
            src_imgs += f'<div class="frame-item"><img src="{uri}" alt="{label}"><span>{label}</span></div>'

        remade_imgs = ""
        for label, img_path in fp["remade_frames"]:
            uri = _img_to_data_uri(img_path)
            remade_imgs += f'<div class="frame-item"><img src="{uri}" alt="{label}"><span>{label}</span></div>'

        seg = fp["segment"]
        prompt_preview = (manifest.prompt[:120] + "...") if len(manifest.prompt) > 120 else manifest.prompt
        task_id = seg.task_id or "-"

        segment_cards.append(f"""
    <div class="segment-card">
      <div class="segment-header">
        <h3>片段 {seg.index:03d}</h3>
        <span class="status status-{seg.status}">{seg.status}</span>
      </div>
      <div class="meta">
        <div>Task ID: <code>{task_id}</code></div>
        <div>Prompt: <em>{prompt_preview}</em></div>
      </div>
      <div class="comparison">
        <div class="side">
          <h4>源视频</h4>
          <div class="frame-row">{src_imgs}</div>
        </div>
        <div class="side">
          <h4>重制视频</h4>
          <div class="frame-row">{remade_imgs}</div>
        </div>
      </div>
    </div>""")

    cards_html = "\n".join(segment_cards)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>weibo 效果验证报告</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, sans-serif;
         background: #f5f5f7; color: #1d1d1f; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 28px; margin-bottom: 8px; }}
  .subtitle {{ color: #86868b; margin-bottom: 24px; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .summary-card {{ background: #fff; border-radius: 12px; padding: 16px 24px;
                   flex: 1; min-width: 140px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .summary-card .num {{ font-size: 32px; font-weight: 700; }}
  .summary-card .label {{ color: #86868b; font-size: 13px; margin-top: 4px; }}
  .segment-card {{ background: #fff; border-radius: 12px; padding: 20px;
                   margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .segment-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
  .segment-header h3 {{ font-size: 18px; }}
  .status {{ padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  .status-succeeded {{ background: #d1fae5; color: #065f46; }}
  .status-failed {{ background: #fee2e2; color: #991b1b; }}
  .status-pending {{ background: #e0e7ff; color: #3730a3; }}
  .meta {{ font-size: 13px; color: #86868b; margin-bottom: 16px; }}
  .meta code {{ background: #f3f4f6; padding: 1px 6px; border-radius: 4px; font-size: 12px; }}
  .comparison {{ display: flex; gap: 24px; }}
  .side {{ flex: 1; }}
  .side h4 {{ font-size: 14px; color: #6b7280; margin-bottom: 8px; text-align: center; }}
  .frame-row {{ display: flex; gap: 8px; }}
  .frame-item {{ flex: 1; text-align: center; }}
  .frame-item img {{ width: 100%; border-radius: 8px; border: 1px solid #e5e7eb; }}
  .frame-item span {{ font-size: 11px; color: #9ca3af; }}
  @media (max-width: 768px) {{
    .comparison {{ flex-direction: column; }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1>weibo 效果验证报告</h1>
  <div class="subtitle">生成时间: {now} &nbsp;|&nbsp; 预设: {manifest.preset} &nbsp;|&nbsp; 源: {Path(manifest.source).name}</div>
  <div class="summary">
    <div class="summary-card"><div class="num">{total}</div><div class="label">总片段</div></div>
    <div class="summary-card"><div class="num">{succeeded}</div><div class="label">成功</div></div>
    <div class="summary-card"><div class="num">{failed}</div><div class="label">失败</div></div>
    <div class="summary-card"><div class="num">{pending}</div><div class="label">待处理</div></div>
  </div>
  {cards_html}
</div>
</body>
</html>"""


def register_verify(app: typer.Typer) -> None:
    @app.command("verify")
    def verify_cmd(
        ctx: typer.Context,
        manifest_path: Path = typer.Argument(..., help="manifest.json 路径。"),
        output: Path = typer.Option(None, "-o", "--output", help="HTML 报告输出路径。"),
        no_open: bool = typer.Option(False, "--no-open", help="不自动打开浏览器。"),
    ) -> None:
        """提取源/重制视频帧，生成 HTML 对比报告。"""
        config: AppConfig = ctx.obj
        manifest = Manifest.load(manifest_path)
        job_dir = manifest_path.parent
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        succeeded = [s for s in manifest.segments if s.status == "succeeded"]
        if not succeeded:
            typer.echo("没有成功的片段可验证。", err=True)
            raise typer.Exit(1)

        typer.echo(f"提取帧用于对比: {len(succeeded)} 个片段")

        frame_pairs: list[dict] = []
        for seg in succeeded:
            src_video = job_dir / seg.source_path
            remade_video = job_dir / seg.remade_path if seg.remade_path else None

            source_frames: list[tuple[str, Path]] = []
            remade_frames: list[tuple[str, Path]] = []

            if src_video.exists():
                frames = extract_multi_frames(src_video, analysis_dir, prefix=f"src_{seg.index:03d}")
                labels = ["首帧", "中帧", "尾帧"]
                for i, f in enumerate(frames):
                    source_frames.append((labels[i] if i < len(labels) else f"帧{i}", f))

            if remade_video and remade_video.exists():
                frames = extract_multi_frames(remade_video, analysis_dir, prefix=f"remade_{seg.index:03d}")
                labels = ["首帧", "中帧", "尾帧"]
                for i, f in enumerate(frames):
                    remade_frames.append((labels[i] if i < len(labels) else f"帧{i}", f))

            if source_frames or remade_frames:
                frame_pairs.append({
                    "segment": seg,
                    "source_frames": source_frames,
                    "remade_frames": remade_frames,
                })

        typer.echo(f"已提取 {sum(len(fp['source_frames']) + len(fp['remade_frames']) for fp in frame_pairs)} 个帧")

        html = _build_html(manifest, job_dir, frame_pairs)
        out_path = output or (job_dir / "report.html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        typer.echo(f"报告已生成: {out_path}")

        if not no_open:
            try:
                webbrowser.open(f"file://{out_path.resolve()}")
            except Exception:
                pass

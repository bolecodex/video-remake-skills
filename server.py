"""Web server wrapping weibo CLI for business users."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
JOBS_DIR = BASE_DIR / "jobs"
UPLOADS_DIR = BASE_DIR / "uploads"
JOBS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="视频重制工作台")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class JobState:
    job_id: str
    status: str = "pending"
    step: str = ""
    progress: str = ""
    source_video: str = ""
    preset: str = "h2v"
    prompt: str = ""
    output_dir: str = ""
    final_video: str | None = None
    report_html: str | None = None
    error: str | None = None
    segments_total: int = 0
    segments_done: int = 0
    log_lines: list[str] = field(default_factory=list)


_jobs: dict[str, JobState] = {}
_lock = threading.Lock()

PRESET_LABELS = {
    "h2v": "横屏转竖屏",
    "style_transfer": "AI 风格转绘",
    "character_swap": "换人换脸",
    "viral_replica": "爆款复刻",
}


def _run_job(job: JobState) -> None:
    """Run the full pipeline in a background thread."""
    job_dir = Path(job.output_dir)
    source = Path(job.source_video)
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    weibo_bin = BASE_DIR / ".venv" / "bin" / "weibo"

    def log(msg: str) -> None:
        with _lock:
            job.log_lines.append(msg)

    def run_cmd(args: list[str], step: str) -> bool:
        job.step = step
        log(f"▶ {step}")
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(BASE_DIR),
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    log(line)
                    if "[OK]" in line:
                        job.segments_done += 1
                        job.progress = f"{job.segments_done}/{job.segments_total}"
            proc.wait()
            if proc.returncode != 0:
                job.error = f"{step} 失败 (exit={proc.returncode})"
                return False
            return True
        except Exception as exc:
            job.error = f"{step} 异常: {exc}"
            return False

    try:
        job.status = "running"

        # Step 1: Split
        if not run_cmd(
            [str(weibo_bin), "split", str(source), "-o", str(job_dir), "--preset", job.preset]
            + (["--prompt", job.prompt] if job.prompt else []),
            "分割视频 + 上传 TOS",
        ):
            job.status = "failed"
            return

        manifest_path = job_dir / "manifest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            job.segments_total = len(m.get("segments", []))

        # Step 2: Asset register (for real-person safety)
        has_segments_with_url = False
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            has_segments_with_url = any(
                s.get("segment_url") and not s["segment_url"].startswith("asset://")
                for s in m.get("segments", [])
            )

        if has_segments_with_url:
            run_cmd(
                [str(weibo_bin), "asset-register", str(manifest_path), "-g", f"web-{job.job_id[:8]}"],
                "注册素材资产（防审核拦截）",
            )

        # Step 3: Remake
        if not run_cmd(
            [str(weibo_bin), "remake", str(manifest_path)],
            "Seedance 2.0 重制",
        ):
            job.status = "failed"
            return

        # Check for failures and retry with asset if needed
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            failed_with_person = any(s.get("status") == "failed" for s in m.get("segments", []))
            if failed_with_person:
                log("检测到失败片段，尝试 Asset 模式重试...")
                run_cmd(
                    [str(weibo_bin), "asset-register", str(manifest_path), "-g", f"web-{job.job_id[:8]}"],
                    "注册失败片段为素材资产",
                )
                run_cmd(
                    [str(weibo_bin), "remake", str(manifest_path)],
                    "重试失败片段",
                )

        # Step 4: Merge
        final_path = job_dir / "final.mp4"
        if not run_cmd(
            [str(weibo_bin), "merge", str(manifest_path), "-o", str(final_path), "--keep-audio"],
            "合并成片",
        ):
            job.status = "failed"
            return

        if final_path.exists():
            job.final_video = str(final_path)

        # Step 5: Verify
        report_path = job_dir / "report.html"
        run_cmd(
            [str(weibo_bin), "verify", str(manifest_path), "-o", str(report_path), "--no-open"],
            "生成对比报告",
        )
        if report_path.exists():
            job.report_html = str(report_path)

        # Final status
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            succeeded = sum(1 for s in m.get("segments", []) if s.get("status") == "succeeded")
            total = len(m.get("segments", []))
            job.segments_done = succeeded
            job.segments_total = total
            job.progress = f"{succeeded}/{total}"

        job.status = "succeeded" if job.final_video else "failed"
        job.step = "完成" if job.status == "succeeded" else "失败"
        log(f"✓ 任务完成: {job.progress} 段成功")

    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        log(f"✗ 异常: {exc}")


# ── API routes ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "frontend.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    preset: str = Form("h2v"),
    prompt: str = Form(""),
):
    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_path = UPLOADS_DIR / f"{job_id}_{video.filename}"
    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    job = JobState(
        job_id=job_id,
        source_video=str(video_path),
        preset=preset,
        prompt=prompt,
        output_dir=str(job_dir),
    )
    with _lock:
        _jobs[job_id] = job

    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()

    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs")
async def list_jobs():
    with _lock:
        result = []
        for j in sorted(_jobs.values(), key=lambda x: x.job_id, reverse=True):
            result.append({
                "job_id": j.job_id,
                "status": j.status,
                "step": j.step,
                "progress": j.progress,
                "preset": j.preset,
                "preset_label": PRESET_LABELS.get(j.preset, j.preset),
                "source_video": Path(j.source_video).name if j.source_video else "",
                "has_final": j.final_video is not None,
                "has_report": j.report_html is not None,
                "error": j.error,
            })
    return result


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, 404)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "step": job.step,
        "progress": job.progress,
        "preset": job.preset,
        "preset_label": PRESET_LABELS.get(job.preset, job.preset),
        "source_video": Path(job.source_video).name,
        "segments_total": job.segments_total,
        "segments_done": job.segments_done,
        "has_final": job.final_video is not None,
        "has_report": job.report_html is not None,
        "error": job.error,
        "log": job.log_lines[-100:],
    }


@app.get("/api/jobs/{job_id}/final")
async def download_final(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job or not job.final_video:
        return JSONResponse({"error": "Final video not available"}, 404)
    return FileResponse(
        job.final_video,
        media_type="video/mp4",
        filename=f"{job.preset}_{Path(job.source_video).stem}_final.mp4",
    )


@app.get("/api/jobs/{job_id}/report")
async def get_report(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job or not job.report_html:
        return JSONResponse({"error": "Report not available"}, 404)
    return FileResponse(job.report_html, media_type="text/html")


@app.get("/api/jobs/{job_id}/source")
async def get_source_video(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job or not job.source_video:
        return JSONResponse({"error": "Source not found"}, 404)
    return FileResponse(job.source_video, media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8899, reload=True)

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
from typing import Any

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


PRESET_META: dict[str, dict[str, str]] = {
    "h2v": {
        "label": "横屏转竖屏",
        "icon": "📐",
        "desc": "16:9 → 9:16",
        "prompt_hint": "竖屏安全区构图，主体居中偏上",
    },
    "v2h": {
        "label": "竖屏转横屏",
        "icon": "🖥",
        "desc": "9:16 → 16:9",
        "prompt_hint": "横屏宽画幅构图，利用横向空间展现完整场景",
    },
    "style_transfer": {
        "label": "AI 风格转绘",
        "icon": "🎨",
        "desc": "保持内容换风格",
        "prompt_hint": "水墨插画风格，写意笔触，留白意境，宣纸质感",
    },
    "character_swap": {
        "label": "换人换脸",
        "icon": "🎭",
        "desc": "替换角色形象",
        "prompt_hint": "将角色替换为银发精灵女战士，尖耳，蓝色铠甲，保持原片动作",
    },
    "viral_replica": {
        "label": "爆款复刻",
        "icon": "🔥",
        "desc": "复刻热门视频",
        "prompt_hint": "复刻镜头语言和节奏，竖屏构图，画面饱满",
    },
}

PRESET_LABELS = {k: v["label"] for k, v in PRESET_META.items()}

PIPELINE_STEPS = [
    {"id": "split", "label": "分割"},
    {"id": "asset", "label": "注册"},
    {"id": "remake", "label": "重制"},
    {"id": "merge", "label": "合并"},
    {"id": "verify", "label": "报告"},
]

STEP_KEY_MAP = {
    "分割视频 + 上传 TOS": "split",
    "注册素材资产（防审核拦截）": "asset",
    "注册失败片段为素材资产": "asset",
    "Seedance 2.0 重制": "remake",
    "重试失败片段": "remake",
    "合并成片": "merge",
    "生成对比报告": "verify",
    "完成": "done",
}


@dataclass
class JobState:
    job_id: str
    status: str = "pending"
    step: str = ""
    step_key: str = ""
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
    batch_id: str | None = None
    created_at: float = 0.0
    score: int | None = None
    score_note: str = ""


_jobs: dict[str, JobState] = {}
_batches: dict[str, list[str]] = {}
_lock = threading.Lock()


def _run_job(job: JobState) -> None:
    """Run the full pipeline in a background thread."""
    job_dir = Path(job.output_dir)
    source = Path(job.source_video)
    weibo_bin = BASE_DIR / ".venv" / "bin" / "weibo"

    def log(msg: str) -> None:
        with _lock:
            job.log_lines.append(msg)

    def run_cmd(args: list[str], step: str) -> bool:
        job.step = step
        job.step_key = STEP_KEY_MAP.get(step, "")
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
            log("等待 30s 让 Asset 在 Seedance 侧生效...")
            time.sleep(30)

        if not run_cmd(
            [str(weibo_bin), "remake", str(manifest_path)],
            "Seedance 2.0 重制",
        ):
            job.status = "failed"
            return

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

        final_path = job_dir / "final.mp4"
        if not run_cmd(
            [str(weibo_bin), "merge", str(manifest_path), "-o", str(final_path), "--keep-audio"],
            "合并成片",
        ):
            job.status = "failed"
            return

        if final_path.exists():
            job.final_video = str(final_path)

        report_path = job_dir / "report.html"
        run_cmd(
            [str(weibo_bin), "verify", str(manifest_path), "-o", str(report_path), "--no-open"],
            "生成对比报告",
        )
        if report_path.exists():
            job.report_html = str(report_path)

        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            succeeded = sum(1 for s in m.get("segments", []) if s.get("status") == "succeeded")
            total = len(m.get("segments", []))
            job.segments_done = succeeded
            job.segments_total = total
            job.progress = f"{succeeded}/{total}"

        job.status = "succeeded" if job.final_video else "failed"
        job.step = "完成" if job.status == "succeeded" else "失败"
        job.step_key = "done" if job.status == "succeeded" else "failed"
        log(f"✓ 任务完成: {job.progress} 段成功")

    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        log(f"✗ 异常: {exc}")


def _job_summary(j: JobState) -> dict[str, Any]:
    return {
        "job_id": j.job_id,
        "status": j.status,
        "step": j.step,
        "step_key": j.step_key,
        "progress": j.progress,
        "preset": j.preset,
        "preset_label": PRESET_LABELS.get(j.preset, j.preset),
        "source_video": Path(j.source_video).name if j.source_video else "",
        "has_final": j.final_video is not None,
        "has_report": j.report_html is not None,
        "error": j.error,
        "batch_id": j.batch_id,
        "created_at": j.created_at,
        "score": j.score,
        "score_note": j.score_note,
    }


# ── API routes ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "frontend.html").read_text(encoding="utf-8")


@app.get("/api/meta/presets")
async def get_presets():
    return PRESET_META


@app.get("/api/meta/steps")
async def get_steps():
    return PIPELINE_STEPS


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    preset: str = Form("h2v"),
    prompt: str = Form(""),
    batch_id: str = Form(""),
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
        batch_id=batch_id or None,
        created_at=time.time(),
    )
    with _lock:
        _jobs[job_id] = job

    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()

    return {"job_id": job_id, "status": "pending"}


@app.post("/api/batch-jobs")
async def create_batch(
    video: UploadFile = File(...),
    presets: str = Form(...),
    prompts: str = Form("{}"),
):
    """Create multiple jobs from one video.

    ``presets`` is a comma-separated string like ``h2v,style_transfer``.
    ``prompts`` is a JSON object like ``{"style_transfer": "水墨风"}``.
    """
    batch_id = uuid.uuid4().hex[:12]
    preset_list = [p.strip() for p in presets.split(",") if p.strip()]
    try:
        prompt_map: dict[str, str] = json.loads(prompts)
    except json.JSONDecodeError:
        prompt_map = {}

    raw_bytes = await video.read()
    job_ids: list[str] = []

    for preset in preset_list:
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        video_path = UPLOADS_DIR / f"{job_id}_{video.filename}"
        video_path.write_bytes(raw_bytes)

        job = JobState(
            job_id=job_id,
            source_video=str(video_path),
            preset=preset,
            prompt=prompt_map.get(preset, ""),
            output_dir=str(job_dir),
            batch_id=batch_id,
            created_at=time.time(),
        )
        with _lock:
            _jobs[job_id] = job
        job_ids.append(job_id)

        t = threading.Thread(target=_run_job, args=(job,), daemon=True)
        t.start()

    with _lock:
        _batches[batch_id] = job_ids

    return {"batch_id": batch_id, "job_ids": job_ids}


@app.get("/api/batch-jobs/{batch_id}")
async def get_batch(batch_id: str):
    with _lock:
        job_ids = _batches.get(batch_id, [])
        jobs_data = [_job_summary(_jobs[jid]) for jid in job_ids if jid in _jobs]
    if not jobs_data:
        return JSONResponse({"error": "Batch not found"}, 404)
    statuses = [j["status"] for j in jobs_data]
    if all(s in ("succeeded", "failed") for s in statuses):
        overall = "completed"
    elif any(s == "running" for s in statuses):
        overall = "running"
    else:
        overall = "pending"
    return {"batch_id": batch_id, "status": overall, "jobs": jobs_data}


@app.get("/api/jobs")
async def list_jobs():
    with _lock:
        result = [_job_summary(j) for j in sorted(_jobs.values(), key=lambda x: x.created_at, reverse=True)]
    return result


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, 404)
    data = _job_summary(job)
    data["segments_total"] = job.segments_total
    data["segments_done"] = job.segments_done
    data["log"] = job.log_lines[-100:]
    return data


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


@app.post("/api/jobs/{job_id}/score")
async def score_job(job_id: str, body: dict):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, 404)
    job.score = int(body.get("score", 0))
    job.score_note = str(body.get("note", ""))
    review_path = Path(job.output_dir) / "review.json"
    review_path.write_text(
        json.dumps({"score": job.score, "note": job.score_note}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"ok": True}


@app.get("/api/gallery")
async def gallery():
    with _lock:
        items = [
            _job_summary(j)
            for j in sorted(_jobs.values(), key=lambda x: x.created_at, reverse=True)
            if j.status == "succeeded"
        ]
    return items


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8899, reload=True)

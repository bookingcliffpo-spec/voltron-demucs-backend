import os
import platform
import shutil
import threading
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import CORS_ORIGINS, MAX_FILE_MB, PUBLIC_BASE_URL, WORK_ROOT, AVAILABLE_MODELS
from app.jobs import jobs
from app.pipeline import run_pipeline

app = FastAPI(title="voltron-demucs-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(WORK_ROOT, exist_ok=True)


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _check_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _check_demucs() -> bool:
    try:
        import demucs  # noqa: F401
        return True
    except ImportError:
        return False


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "voltron-demucs-backend",
        "ffmpeg": _check_ffmpeg(),
        "python": True,
        "torch": _check_torch(),
        "demucs": _check_demucs(),
    }


@app.get("/api/diagnostics")
def diagnostics():
    disk = shutil.disk_usage(WORK_ROOT)
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "disk": {
            "total_gb": round(disk.total / 1e9, 2),
            "used_gb": round(disk.used / 1e9, 2),
            "free_gb": round(disk.free / 1e9, 2),
        },
        "available_models": AVAILABLE_MODELS,
        "cors_origins": CORS_ORIGINS,
        "active_jobs": jobs.count_active(),
        "total_jobs_tracked": jobs.count_all(),
        "ffmpeg": _check_ffmpeg(),
        "torch": _check_torch(),
        "demucs": _check_demucs(),
    }


def _backend_url(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


@app.post("/api/separate")
async def separate(
    request: Request,
    file: UploadFile = File(...),
    model: str | None = Form(None),
    mode: str = Form("4stems"),
):
    if mode not in ("4stems", "2stems"):
        raise HTTPException(status_code=400, detail="mode must be '4stems' or '2stems'")

    job = jobs.create(mode=mode, requested_model=model)
    job.temp_dir = os.path.join(WORK_ROOT, job.job_id)
    os.makedirs(job.temp_dir, exist_ok=True)

    local_path = os.path.join(job.temp_dir, file.filename or f"{uuid.uuid4().hex}.wav")
    size = 0
    max_bytes = MAX_FILE_MB * 1024 * 1024
    with open(local_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                shutil.rmtree(job.temp_dir, ignore_errors=True)
                raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_FILE_MB}MB upload limit.")
            f.write(chunk)

    thread = threading.Thread(target=run_pipeline, args=(job, None, None, local_path), daemon=True)
    thread.start()

    return {"success": True, "job_id": job.job_id, "backend_url": _backend_url(request), "status": "queued"}


@app.post("/api/separate_url")
async def separate_url(request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")
    file_url = body.get("file_url")
    filename = body.get("filename") or "input"
    model = body.get("model")
    mode = body.get("mode", "4stems")

    if not file_url:
        raise HTTPException(status_code=400, detail="file_url is required")
    if mode not in ("4stems", "2stems"):
        raise HTTPException(status_code=400, detail="mode must be '4stems' or '2stems'")

    job = jobs.create(mode=mode, requested_model=model)

    thread = threading.Thread(target=run_pipeline, args=(job, file_url, filename, None), daemon=True)
    thread.start()

    return {"success": True, "job_id": job.job_id, "backend_url": _backend_url(request), "status": "queued"}


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_public_dict()


@app.get("/api/download/{job_id}/zip")
def download_zip(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "complete" or not job.zip_path or not os.path.exists(job.zip_path):
        raise HTTPException(status_code=409, detail="job is not completed yet")
    return FileResponse(job.zip_path, media_type="application/zip", filename=f"{job_id}_stems.zip")


@app.get("/api/download/{job_id}/{stem}")
def download_stem(job_id: str, stem: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "complete":
        raise HTTPException(status_code=409, detail="job is not completed yet")
    path = job.stems.get(stem)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"stem '{stem}' not found for this job")
    return FileResponse(path, media_type="audio/wav", filename=f"{stem}.wav")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": str(exc.detail)},
    )

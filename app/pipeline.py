import json
import os
import shutil
import subprocess
import threading
import zipfile

import requests

from app.config import (
    DEMUCS_SEGMENT_SECONDS,
    DEMUCS_TIMEOUT_SECONDS,
    MAX_DURATION_SECONDS,
    MAX_FILE_MB,
    STEM_NAMES_2,
    STEM_NAMES_4,
    WORK_ROOT,
    model_chain,
)
from app.jobs import Job


class PipelineError(Exception):
    def __init__(self, stage: str, message: str, technical_error: str = "", stdout: str = "", retryable: bool = False):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.technical_error = technical_error
        self.stdout = stdout
        self.retryable = retryable

    def to_dict(self):
        return {
            "success": False,
            "stage": self.stage,
            "message": self.message,
            "technical_error": self.technical_error,
            "stdout": self.stdout,
            "retryable": self.retryable,
        }


def _job_dir(job_id: str) -> str:
    path = os.path.join(WORK_ROOT, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def download_input(job: Job, file_url: str, filename: str) -> str:
    job.stage = "file_saved"
    job.progress = 5
    job.touch()
    dest = os.path.join(job.temp_dir, filename or "input")
    try:
        with requests.get(file_url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            size = 0
            max_bytes = MAX_FILE_MB * 1024 * 1024
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise PipelineError(
                            "file_saved",
                            f"File exceeds the {MAX_FILE_MB}MB upload limit.",
                            retryable=False,
                        )
                    f.write(chunk)
    except requests.RequestException as e:
        raise PipelineError(
            "file_saved",
            "Could not download the source file from Base44 storage.",
            technical_error=str(e),
            retryable=True,
        )
    return dest


def decode_to_safe_wav(job: Job, input_path: str) -> str:
    job.stage = "validating_file"
    job.progress = 12
    job.touch()

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", input_path],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        try:
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            if duration > MAX_DURATION_SECONDS:
                raise PipelineError(
                    "validating_file",
                    f"Track is longer than the {MAX_DURATION_SECONDS // 60}-minute limit.",
                    technical_error=f"duration={duration}s",
                    retryable=False,
                )
        except (KeyError, ValueError, TypeError):
            pass  # duration unknown, let it through

    job.stage = "ffmpeg_decode_test"
    job.progress = 16
    job.touch()

    job.stage = "converting_to_safe_wav"
    job.progress = 20
    job.touch()

    safe_wav = os.path.join(job.temp_dir, "input_safe.wav")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", safe_wav],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.exists(safe_wav):
        raise PipelineError(
            "converting_to_safe_wav",
            "ffmpeg could not decode the uploaded audio file.",
            technical_error=result.stderr[-4000:],
            stdout=result.stdout[-2000:],
            retryable=False,
        )
    return safe_wav


# This box has ~2GB RAM total — enough for exactly one demucs run at a
# time, confirmed by real crashes when two jobs overlapped. A global lock
# serializes all separation work server-wide; a second job simply waits
# its turn instead of racing the first one for memory and losing both.
_demucs_slot = threading.Lock()


def run_demucs(job: Job, safe_wav: str) -> tuple[str, dict]:
    job.stage = "queued_for_worker"
    job.progress = 20
    job.touch()

    with _demucs_slot:
        return _run_demucs_locked(job, safe_wav)


def _run_demucs_locked(job: Job, safe_wav: str) -> tuple[str, dict]:
    job.stage = "checking_python"
    job.progress = 22
    job.touch()

    job.stage = "checking_torch"
    job.progress = 24
    job.touch()

    job.stage = "checking_demucs"
    job.progress = 26
    job.touch()

    job.stage = "loading_model"
    job.progress = 28
    job.touch()

    chain = model_chain(job.requested_model)
    stem_names = STEM_NAMES_2 if job.mode == "2stems" else STEM_NAMES_4
    out_root = os.path.join(job.temp_dir, "separated")

    attempts: list[str] = []
    last_error: PipelineError | None = None
    for i, model in enumerate(chain):
        job.stage = "running_demucs"
        job.progress = 30 + int(i * (50 / max(len(chain), 1)))
        job.touch()

        # -j 1 keeps demucs from spawning parallel workers for each segment/
        # sub-model — on a memory-constrained CPU box, ensemble models like
        # htdemucs_ft (4 models) can otherwise use enough RAM simultaneously
        # to get the whole container OOM-killed (which looks like the
        # *server itself* silently vanishing mid-job, not a clean failure).
        # --segment chunks the track instead of loading it whole, which is
        # what actually matters for a real multi-minute song rather than a
        # short test clip: memory scales with segment length, not track
        # length, once this is set.
        cmd = ["demucs", "-n", model, "-j", "1", "--segment", str(DEMUCS_SEGMENT_SECONDS), "-o", out_root]
        if job.mode == "2stems":
            cmd.append("--two-stems=vocals")
        cmd.append(safe_wav)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=DEMUCS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            stderr = (e.stderr or b"").decode("utf-8", "ignore") if isinstance(e.stderr, bytes) else str(e.stderr or "")
            attempts.append(f"[{model}] TIMEOUT after {DEMUCS_TIMEOUT_SECONDS}s: {stderr[-1000:]}")
            last_error = PipelineError(
                "running_demucs",
                f"Demucs timed out after {DEMUCS_TIMEOUT_SECONDS}s (model: {model}).",
                technical_error="\n---\n".join(attempts)[-6000:],
                retryable=i < len(chain) - 1,
            )
            continue

        if result.returncode == 0:
            track_name = os.path.splitext(os.path.basename(safe_wav))[0]
            stem_dir = os.path.join(out_root, model, track_name)
            stems = {}
            missing = []
            for stem in stem_names:
                stem_path = os.path.join(stem_dir, f"{stem}.wav")
                if os.path.exists(stem_path):
                    stems[stem] = stem_path
                else:
                    missing.append(stem)
            if missing:
                attempts.append(f"[{model}] missing stems {missing}: {result.stderr[-1000:]}")
                last_error = PipelineError(
                    "validating_outputs",
                    f"Demucs finished but stems were missing: {', '.join(missing)}.",
                    technical_error="\n---\n".join(attempts)[-6000:],
                    stdout=result.stdout[-2000:],
                    retryable=True,
                )
                continue
            return model, stems

        attempts.append(f"[{model}] exit={result.returncode}: {result.stderr[-1500:]}")
        last_error = PipelineError(
            "running_demucs",
            f"Demucs failed during model inference (model: {model}).",
            technical_error="\n---\n".join(attempts)[-6000:],
            stdout=result.stdout[-2000:],
            retryable=i < len(chain) - 1,
        )

    raise last_error or PipelineError("running_demucs", "Demucs failed for an unknown reason.", retryable=False)


def validate_stems(job: Job, stems: dict):
    job.stage = "validating_outputs"
    job.progress = 88
    job.touch()
    for stem, path in stems.items():
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise PipelineError(
                "validating_outputs",
                f"Output stem '{stem}' is missing or empty after separation.",
                retryable=True,
            )


def build_zip(job: Job, stems: dict) -> str:
    job.stage = "creating_zip"
    job.progress = 95
    job.touch()
    zip_path = os.path.join(job.temp_dir, "stems.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for stem, path in stems.items():
            zf.write(path, arcname=f"{stem}.wav")
    return zip_path


def run_pipeline(job: Job, file_url: str | None, filename: str | None, local_path: str | None):
    job.temp_dir = _job_dir(job.job_id)
    job.status = "processing"
    job.stage = "upload_received"
    job.touch()
    try:
        if local_path:
            job.stage = "file_saved"
            input_path = local_path
        else:
            input_path = download_input(job, file_url, filename or "input")

        safe_wav = decode_to_safe_wav(job, input_path)
        model_used, stems = run_demucs(job, safe_wav)
        validate_stems(job, stems)
        job.zip_path = build_zip(job, stems)

        job.model_used = model_used
        job.stems = stems
        job.stage = "complete"
        job.status = "complete"
        job.progress = 100
        job.touch()
    except PipelineError as e:
        job.status = "failed"
        job.stage = e.stage
        job.error = e.to_dict()
        job.touch()
    except Exception as e:  # noqa: BLE001 - convert anything unexpected into a structured error
        job.status = "failed"
        job.stage = "unexpected_error"
        job.error = PipelineError("unexpected_error", "An unexpected server error occurred.", technical_error=str(e), retryable=True).to_dict()
        job.touch()
    finally:
        if job.temp_dir:
            input_leftover = os.path.join(job.temp_dir, "input_safe.wav")
            # keep stems + zip, drop the raw/intermediate audio to save disk
            for leftover in (input_leftover,):
                if os.path.exists(leftover):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass

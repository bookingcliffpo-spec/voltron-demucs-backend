import os


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


DEMUCS_DEFAULT_MODEL = os.environ.get("DEMUCS_DEFAULT_MODEL", "htdemucs")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "100"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "600"))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

DEFAULT_CORS_ORIGINS = [
    "https://voltron-master-flow.base44.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

CORS_ORIGINS = DEFAULT_CORS_ORIGINS + _env_list("EXTRA_CORS_ORIGINS")

MODEL_CHAIN_BASE = ["htdemucs_ft", "htdemucs", "mdx_extra_q"]
AVAILABLE_MODELS = ["htdemucs_ft", "htdemucs", "mdx_extra_q", "hdemucs_mmi"]

WORK_ROOT = os.environ.get("WORK_ROOT", "/tmp/voltron_jobs")

STEM_NAMES_4 = ["vocals", "drums", "bass", "other"]
STEM_NAMES_2 = ["vocals", "no_vocals"]


def model_chain(requested: str | None) -> list[str]:
    """Build the ordered list of models to try for a job.

    An explicitly requested model is tried first; the rest of the standard
    chain (used to auto-recover from OOM / weight download failures on a
    single model) follows, minus duplicates.
    """
    requested = (requested or "").strip()
    if requested and requested != "auto":
        first = requested
    else:
        first = DEMUCS_DEFAULT_MODEL
    chain = [first] + [m for m in MODEL_CHAIN_BASE if m != first]
    # de-dupe while preserving order
    seen = set()
    ordered = []
    for m in chain:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered

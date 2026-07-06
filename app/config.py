import os


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


DEMUCS_DEFAULT_MODEL = os.environ.get("DEMUCS_DEFAULT_MODEL", "htdemucs")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "100"))
MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", "600"))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))
DEMUCS_TIMEOUT_SECONDS = int(os.environ.get("DEMUCS_TIMEOUT_SECONDS", "900"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

DEFAULT_CORS_ORIGINS = [
    "https://voltron-master-flow.base44.app",
    "https://app.base44.com",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

CORS_ORIGINS = DEFAULT_CORS_ORIGINS + _env_list("EXTRA_CORS_ORIGINS")

# Also match any Base44 editor/preview/published subdomain (e.g. the editor
# runs on app.base44.com, published apps get a *.base44.app subdomain, and
# Base44 may assign other preview subdomains we can't fully enumerate).
CORS_ORIGIN_REGEX = r"^https://([a-zA-Z0-9-]+\.)*base44\.(app|com)$"

MODEL_CHAIN_BASE = ["htdemucs_ft", "htdemucs", "mdx_extra_q"]
AVAILABLE_MODELS = ["htdemucs_ft", "htdemucs", "mdx_extra_q", "hdemucs_mmi"]

WORK_ROOT = os.environ.get("WORK_ROOT", "/tmp/voltron_jobs")

STEM_NAMES_4 = ["vocals", "drums", "bass", "other"]
STEM_NAMES_2 = ["vocals", "no_vocals"]


def model_chain(requested: str | None) -> list[str]:
    """Build the ordered list of models to try for a job.

    DEMUCS_DEFAULT_MODEL always goes first: it's the only model baked into
    the Docker image at build time (see Dockerfile), so it needs no runtime
    download and runs fastest on a CPU-only box. The Base44 proxy always
    asks for "htdemucs_ft" (a slower 4-model ensemble) by default, which
    would otherwise always run first and eat most of the time budget before
    ever falling back to the fast path. The requested model still gets a
    turn — just after the pre-cached default rather than before it.
    """
    requested = (requested or "").strip()
    chain = [DEMUCS_DEFAULT_MODEL]
    if requested and requested not in ("auto", DEMUCS_DEFAULT_MODEL):
        chain.append(requested)
    for m in MODEL_CHAIN_BASE:
        if m not in chain:
            chain.append(m)
    return chain

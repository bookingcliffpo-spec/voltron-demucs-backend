import os


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


DEMUCS_DEFAULT_MODEL = os.environ.get("DEMUCS_DEFAULT_MODEL", "htdemucs")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "100"))
# Real crashes on this 2GB box, with hard memory data: a 20s clip peaked
# ~1700MB (safe); a 180s track in 4stems mode climbed past 1900MB and over
# the 2147.5MB limit before finishing. Chunked processing (--segment) caps
# per-inference working memory but NOT the accumulated output buffers for
# every stem across the full track length — that scales with duration x
# stem count regardless of segment size, and is what actually OOMs a long
# job. Rather than let an over-budget track silently crash the whole
# server, reject it upfront with a clear error. 4stems holds 2x the output
# buffers of 2stems, so it gets a tighter cap. Raise these once the Render
# plan has more RAM (Pro = 4GB per the original deployment spec).
MAX_DURATION_SECONDS_4STEMS = int(os.environ.get("MAX_DURATION_SECONDS_4STEMS", "150"))
MAX_DURATION_SECONDS_2STEMS = int(os.environ.get("MAX_DURATION_SECONDS_2STEMS", "300"))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))
DEMUCS_TIMEOUT_SECONDS = int(os.environ.get("DEMUCS_TIMEOUT_SECONDS", "900"))
# htdemucs loads the ENTIRE track into memory at once unless told to chunk
# it. A 20s test clip fit fine; a real 3-4 min song does not on a 2GB box.
# --segment processes the track in overlapping chunks of this many seconds,
# keeping peak memory roughly flat regardless of track length. htdemucs was
# trained with a 7.8s context window, so this stays at or under that.
DEMUCS_SEGMENT_SECONDS = int(os.environ.get("DEMUCS_SEGMENT_SECONDS", "5"))
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

MODEL_CHAIN_BASE = ["htdemucs", "mdx_extra_q"]
AVAILABLE_MODELS = ["htdemucs", "mdx_extra_q", "htdemucs_ft", "hdemucs_mmi"]

# htdemucs_ft is a 4-model ensemble that needs meaningfully more RAM than a
# single model. Confirmed live: it OOM-kills the whole container on a
# Standard-plan box (2GB), even with demucs's own "-j 1" worker limit,
# wiping all in-memory job state and looking like the job vanished. This
# matches the original spec's own guidance ("Pro (4GB) for htdemucs_ft on
# full-length tracks") — it's excluded from the automatic chain entirely
# until the Render plan is upgraded to Pro, regardless of what a client
# requests, since the Base44 proxy defaults every request to htdemucs_ft
# and would otherwise crash the container on every single job.
EXCLUDED_MODELS = {"htdemucs_ft"}

WORK_ROOT = os.environ.get("WORK_ROOT", "/tmp/voltron_jobs")

STEM_NAMES_4 = ["vocals", "drums", "bass", "other"]
STEM_NAMES_2 = ["vocals", "no_vocals"]


def model_chain(requested: str | None) -> list[str]:
    """Build the ordered list of models to try for a job.

    DEMUCS_DEFAULT_MODEL always goes first: it's the only model baked into
    the Docker image at build time (see Dockerfile), so it needs no runtime
    download and runs fastest on a CPU-only box. The client's requested
    model gets a turn right after, unless it's in EXCLUDED_MODELS (see
    above) — those are silently skipped in favor of the safe chain rather
    than crashing the container.
    """
    requested = (requested or "").strip()
    chain = [DEMUCS_DEFAULT_MODEL]
    if requested and requested not in ("auto", DEMUCS_DEFAULT_MODEL) and requested not in EXCLUDED_MODELS:
        chain.append(requested)
    for m in MODEL_CHAIN_BASE:
        if m not in chain:
            chain.append(m)
    return chain

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
    # TEMPORARY DIAGNOSTIC: force a single model attempt, no fallback chain.
    # Live memory instrumentation showed a real job crossing 75% of the
    # container's 2GB limit only once it moved past the first model into a
    # second one in the same process — this isolates whether the *first*
    # model (htdemucs) completes cleanly on its own within budget, or
    # whether even one model alone is too tight for this plan. Revert once
    # that's answered.
    return [DEMUCS_DEFAULT_MODEL]

    requested = (requested or "").strip()  # noqa: F841 - unreachable, see above
    chain = [DEMUCS_DEFAULT_MODEL]
    if requested and requested not in ("auto", DEMUCS_DEFAULT_MODEL) and requested not in EXCLUDED_MODELS:
        chain.append(requested)
    for m in MODEL_CHAIN_BASE:
        if m not in chain:
            chain.append(m)
    return chain

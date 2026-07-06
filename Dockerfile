FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .

# CPU-only torch/torchaudio wheels — the default PyPI wheels pull in CUDA and
# balloon the image; Render web services have no GPU.
RUN pip install --no-cache-dir torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DEMUCS_DEFAULT_MODEL=htdemucs

# Pre-download every model in the retry chain at build time so no request
# ever pays for a runtime weight download (htdemucs_ft alone is a 4-model
# ensemble that can be several hundred MB).
RUN python -c "\
from demucs.pretrained import get_model; \
[get_model(m) for m in ['htdemucs', 'htdemucs_ft', 'mdx_extra_q']]"

ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

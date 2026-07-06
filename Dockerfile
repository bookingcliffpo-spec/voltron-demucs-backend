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

# Pre-download the default model's weights at build time so the first real
# request doesn't pay for a multi-hundred-MB download on a cold container.
RUN python -c "from demucs.pretrained import get_model; import os; get_model(os.environ.get('DEMUCS_DEFAULT_MODEL', 'htdemucs'))"

ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

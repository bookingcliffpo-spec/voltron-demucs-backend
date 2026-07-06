#!/usr/bin/env python3
"""End-to-end smoke test for the Voltron Demucs backend.

Usage:
    pip install -r requirements-test.txt
    python test_demucs_backend.py https://your-service.onrender.com
"""
import io
import sys
import time

import numpy as np
import requests
import soundfile as sf

TIMEOUT_SECONDS = 15 * 60
POLL_INTERVAL = 5


def make_test_wav() -> bytes:
    """3 seconds of stereo sine tones — enough for demucs to run on quickly."""
    sr = 44100
    duration = 3
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    left = 0.2 * np.sin(2 * np.pi * 220 * t)
    right = 0.2 * np.sin(2 * np.pi * 440 * t)
    audio = np.stack([left, right], axis=1).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    return condition


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_demucs_backend.py <base_url>")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    results = []

    # 1. /health
    try:
        r = requests.get(f"{base_url}/health", timeout=30)
        health = r.json()
        results.append(check("GET /health returns 200", r.status_code == 200))
        results.append(check("health.ok is true", health.get("ok") is True, health))
        results.append(check("ffmpeg available", health.get("ffmpeg") is True, health))
        results.append(check("torch available", health.get("torch") is True, health))
        results.append(check("demucs available", health.get("demucs") is True, health))
    except Exception as e:
        print(f"[FAIL] GET /health raised: {e}")
        results.append(False)

    # 2. /api/diagnostics
    try:
        r = requests.get(f"{base_url}/api/diagnostics", timeout=30)
        diag = r.json()
        results.append(check("GET /api/diagnostics returns 200", r.status_code == 200))
        print(f"       diagnostics: {diag}")
    except Exception as e:
        print(f"[FAIL] GET /api/diagnostics raised: {e}")
        results.append(False)

    # 3. Structured error on bad separate_url request
    try:
        r = requests.post(f"{base_url}/api/separate_url", json={}, timeout=30)
        results.append(check("POST /api/separate_url with no file_url returns 4xx", 400 <= r.status_code < 500))
    except Exception as e:
        print(f"[FAIL] POST /api/separate_url (bad request) raised: {e}")
        results.append(False)

    # 4. Real separation via multipart upload
    job_id = None
    try:
        wav_bytes = make_test_wav()
        files = {"file": ("test_tone.wav", wav_bytes, "audio/wav")}
        data = {"mode": "2stems"}
        r = requests.post(f"{base_url}/api/separate", files=files, data=data, timeout=60)
        results.append(check("POST /api/separate returns 200", r.status_code == 200, r.text))
        payload = r.json()
        job_id = payload.get("job_id")
        results.append(check("response includes job_id", bool(job_id), payload))
    except Exception as e:
        print(f"[FAIL] POST /api/separate raised: {e}")
        results.append(False)

    if job_id:
        print(f"       polling job {job_id} (cold start can take 30-60s, separation a few minutes)...")
        start = time.time()
        final_status = None
        while time.time() - start < TIMEOUT_SECONDS:
            try:
                r = requests.get(f"{base_url}/api/job/{job_id}", timeout=30)
                status = r.json()
            except Exception as e:
                print(f"       poll error: {e}")
                time.sleep(POLL_INTERVAL)
                continue

            print(f"       stage={status.get('stage')} progress={status.get('progress')}% status={status.get('status')}")
            if status.get("status") in ("complete", "failed"):
                final_status = status
                break
            time.sleep(POLL_INTERVAL)

        results.append(check("job reached a terminal state within timeout", final_status is not None))
        if final_status:
            results.append(check("job completed successfully", final_status.get("status") == "complete", final_status))

            if final_status.get("status") == "complete":
                stems = final_status.get("stems", {})
                results.append(check("stems dict is non-empty", len(stems) > 0, final_status))
                for stem in stems:
                    try:
                        r = requests.get(f"{base_url}/api/download/{job_id}/{stem}", timeout=60)
                        results.append(check(f"download stem '{stem}' returns audio", r.status_code == 200 and len(r.content) > 0))
                    except Exception as e:
                        print(f"[FAIL] download stem '{stem}' raised: {e}")
                        results.append(False)

                try:
                    r = requests.get(f"{base_url}/api/download/{job_id}/zip", timeout=60)
                    results.append(check("download zip returns data", r.status_code == 200 and len(r.content) > 0))
                except Exception as e:
                    print(f"[FAIL] download zip raised: {e}")
                    results.append(False)

    print()
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"==> {passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

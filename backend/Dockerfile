# foghorn backend — FastAPI + in-process APScheduler nightly scrape.
# The SQLite DB lives on a mounted volume (FOGHORN_DB_PATH, set in compose).
#
# The [rapidocr] extra is the cross-platform OCR engine for the flyer-venue
# scrapers (Little Hill Lounge, Poor House Bistro) — Apple Vision is the
# engine on macOS but doesn't exist on Linux. It pulls onnxruntime (~200MB);
# drop the extra if image size ever matters more than those two venues.

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[rapidocr]"

# /data is normally a compose volume; created here too so the image also
# runs bare (docker run) without an explicit mount.
RUN mkdir /data
ENV FOGHORN_DB_PATH=/data/foghorn.db

EXPOSE 8100
CMD ["uvicorn", "foghorn.api:app", "--host", "0.0.0.0", "--port", "8100"]

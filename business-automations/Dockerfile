FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
# ffmpeg pulls the sound out of a video, for the video example
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
# Each job and service overrides this with the example it runs.
CMD ["uv", "run", "--no-dev", "python", "examples/01-hello_job.py"]

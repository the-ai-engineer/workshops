FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
# Every job and service uses this one image, each with its own command (see deploy.sh).
CMD ["uv", "run", "--no-dev", "python", "automations/01_manual.py"]

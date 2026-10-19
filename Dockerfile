FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/cambc

ARG PUID=1000
ARG PGID=1000

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --non-unique --gid "${PGID}" cambc \
    && useradd --uid "${PUID}" --gid cambc --create-home --shell /usr/sbin/nologin cambc \
    && python -m pip install --no-cache-dir --disable-pip-version-check cambc==2.2.3 \
    && mkdir -p /app/matches /app/bots/experiments /app/.cambc /app/dist \
    && chown -R cambc:cambc /app /home/cambc

WORKDIR /app

COPY --chown=cambc:cambc cambc.toml ./cambc.toml
COPY --chown=cambc:cambc best_version_registry.json* ./
COPY --chown=cambc:cambc tools/ ./tools/
COPY --chown=cambc:cambc bots/submission-v6/ ./bots/submission-v6/
COPY --chown=cambc:cambc bots/submission-v9/ ./bots/submission-v9/
COPY --chown=cambc:cambc bots/baseline-cpp/ ./bots/baseline-cpp/
COPY --chown=cambc:cambc maps/ ./maps/
COPY --chown=cambc:cambc sdk/ ./sdk/
COPY --chown=cambc:cambc cmake/ ./cmake/

USER cambc
CMD ["python", "tools/run_autonomous_agent.py", "run", "--cycles", "999999", "--interval", "300"]


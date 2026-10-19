FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/cambc

ARG PUID=1000
ARG PGID=1000

RUN groupadd --non-unique --gid "${PGID}" cambc \
    && useradd --uid "${PUID}" --gid cambc --create-home --shell /usr/sbin/nologin cambc \
    && python -m pip install --no-cache-dir --disable-pip-version-check cambc==2.2.5 \
    && mkdir -p /app/matches /app/bots/experiments /app/.cambc \
    && chown -R cambc:cambc /app /home/cambc

WORKDIR /app

COPY --chown=cambc:cambc cambc.toml ./cambc.toml
COPY --chown=cambc:cambc tools/ ./tools/
COPY --chown=cambc:cambc bots/submission-v6/ ./bots/submission-v6/
COPY --chown=cambc:cambc bots/baseline-cpp/ ./bots/baseline-cpp/
COPY --chown=cambc:cambc maps/ ./maps/
COPY --chown=cambc:cambc sdk/ ./sdk/
COPY --chown=cambc:cambc cmake/ ./cmake/

USER cambc
CMD ["python", "tools/fireworks_match_agent.py"]

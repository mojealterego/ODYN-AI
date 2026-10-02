FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin odynworker

WORKDIR /app
COPY odyn_ai/core/mcp_worker.py /app/mcp_worker.py
RUN chown -R 65532:65532 /app

USER 65532:65532
ENTRYPOINT ["python", "/app/mcp_worker.py"]

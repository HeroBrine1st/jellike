ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS transformer

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=Pipfile,target=Pipfile \
    --mount=type=bind,source=Pipfile.lock,target=Pipfile.lock \
    pip install pipenv && pipenv requirements > requirements.txt

FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=transformer /requirements.txt /requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt --prefix=/install

FROM python:${PYTHON_VERSION}-slim AS runner

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /install /usr/local/
COPY jellike jellike

USER nobody

ENV HOST=0.0.0.0
ENV PORT=8000

ENTRYPOINT ["/bin/bash"]

# Needs shell interpolation
CMD ["-c", "exec python3 -m uvicorn jellike:app --host=$HOST --port=$PORT"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --start-interval=1s \
  CMD curl -f http://localhost:$PORT/health || exit 1

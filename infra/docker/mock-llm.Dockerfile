FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY packages/core ./packages/core
COPY apps/mock-llm ./apps/mock-llm
RUN pip install ./packages/core ./apps/mock-llm \
 && useradd --system --uid 10001 sc
USER sc
EXPOSE 8190
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8190/healthz')"
CMD ["mock-llm"]

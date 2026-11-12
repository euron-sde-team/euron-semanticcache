FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY packages/core ./packages/core
COPY apps/api ./apps/api
RUN pip install ./packages/core ./apps/api \
 && useradd --system --uid 10001 sc
USER sc
EXPOSE 8180
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8180/healthz')"
CMD ["semanticcache-api", "serve"]

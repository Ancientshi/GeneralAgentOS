FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GAOS_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir '.[mcp]' \
    && useradd --uid 10001 --create-home agent \
    && mkdir -p /data /profiles && chown agent:agent /data /profiles
COPY examples/assistant.yaml /profiles/profile.yaml
COPY examples/docker.yaml /profiles/docker.yaml
USER agent
EXPOSE 7777
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7777/health', timeout=2)"
ENTRYPOINT ["gaos"]
CMD ["serve", "--profile", "/profiles/profile.yaml", "--profile", "/profiles/docker.yaml"]

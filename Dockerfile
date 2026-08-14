FROM python:3.11-slim

# System deps: git (clone upstream), exiftool, magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    git exiftool libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone original toolkit (optionally pin a commit via build arg)
ARG UPSTREAM_COMMIT=
RUN git clone --depth 1 https://github.com/guillaumemeyer/watermarks-remover.git upstream/watermarks-remover \
    && if [ -n "${UPSTREAM_COMMIT}" ]; then \
         cd upstream/watermarks-remover \
         && git fetch --depth 1 origin ${UPSTREAM_COMMIT} \
         && git checkout -q ${UPSTREAM_COMMIT}; \
       fi

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app ./app

# Runtime dirs
RUN mkdir -p uploads/raw uploads/cleaned uploads/backups

# Non-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
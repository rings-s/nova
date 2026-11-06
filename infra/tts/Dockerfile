# NOVA TTS: Sara's Saudi voice (server.py, ADR-0018).
#
#   GPU (production): the default TORCH_INDEX, CUDA 12.8 wheels; run with
#                     infra/docker-compose.gpu.yml, which reserves the GPU.
#   CPU (dev only):   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
#                     Works, but far slower than a phone turn allows.
FROM python:3.12.11-slim-bookworm

ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
ARG TORCH_VERSION=2.8.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models

# sox: the `sox` package qwen-tts imports shells out to it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sox \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --index-url "${TORCH_INDEX}" "torch==${TORCH_VERSION}" "torchaudio==${TORCH_VERSION}"

COPY requirements.txt /srv/requirements.txt
RUN pip install --no-deps qwen-tts==0.1.1 \
    && grep -v '^qwen-tts' /srv/requirements.txt > /tmp/deps.txt \
    && pip install -r /tmp/deps.txt \
    && rm /tmp/deps.txt

# Non-root. /models is the Hugging Face cache, a named volume in compose, so
# the weights download once; created here so the volume inherits the owner.
RUN useradd --uid 10001 --create-home tts \
    && mkdir -p /models \
    && chown tts:tts /models
COPY --chown=tts:tts server.py /srv/server.py
USER tts
WORKDIR /srv

EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=4)"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8091"]

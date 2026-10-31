# Reproducible environment for the project: CAGE-4 simulator + our code + the Blue side + tests. CPU only.
#
#   docker build -t purple-team .
#   docker run --rm purple-team                      # runs the whole test suite
#   docker run --rm -v "$PWD/results:/app/results" purple-team python scripts/hello_agents.py --seed 0
#
# Not in the image on purpose: the local LLM server (llama.cpp llama-server + GGUF models). The Blue / Red LLM agents talk to a
# server over HTTP (--llama-server URL), so run it on the host (GPU) and pass the URL; see docs/llm-speed-benchmark.md.
FROM python:3.12-slim

# CAGE-4 is pinned by commit: the simulator is the one part of the stack that must never drift under an experiment.
ARG CAGE4_COMMIT=8c3c50ca54b176c2de199847944e8dcc035497e3
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# 1) Python dependencies first, so editing code does not reinstall them. Top-level pins + a full lock for Python 3.12 / Linux.
COPY requirements.txt requirements-dev.txt constraints-py312.txt ./
RUN pip install -r requirements.txt -c constraints-py312.txt \
 && pip install -r requirements-dev.txt

# 2) CAGE-4 at the pinned commit (not a pip package: it is put on PYTHONPATH, as in docs/setup.md).
RUN git clone --quiet https://github.com/cage-challenge/cage-challenge-4.git external/cage-challenge-4 \
 && git -C external/cage-challenge-4 checkout --quiet "${CAGE4_COMMIT}" \
 && rm -rf external/cage-challenge-4/.git
ENV PYTHONPATH=/app:/app/external/cage-challenge-4

# 3) The project itself.
COPY . .
RUN chown -R app:app /app
USER app

CMD ["python", "-m", "pytest", "-q"]

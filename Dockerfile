# Dockerfile for RAE-Hive Agent Swarm
# Enterprise Grade Python 3.14 Environment

FROM ubuntu:22.04 AS builder

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Python 3.14 via deadsnakes
RUN apt-get update && apt-get install -y \
    software-properties-common curl git build-essential \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.14 python3.14-dev python3.14-venv \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.14
RUN ln -sf /usr/bin/python3.14 /usr/bin/python3

WORKDIR /app

# Install dependencies in a virtualenv
RUN python3.14 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY packages/rae-hive/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir fastapi uvicorn httpx structlog pyyaml

# STAGE 2: Final Runtime
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y \
    software-properties-common curl \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y python3.14 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy base agent code
COPY packages/rae-hive/base_agent /app/base_agent
COPY packages/rae-hive/config /app/config
COPY packages/rae-hive/hive_engine.py /app/hive_engine.py
COPY packages/rae-hive/planner.py /app/planner.py
# COPY rae_libs /app/rae_libs

# Create work directory
RUN mkdir -p /app/work_dir

# Create a non-root user
RUN useradd -m -u 1000 hiveuser && \
    chown -R hiveuser:hiveuser /app
USER hiveuser

# Default command
CMD ["python", "hive_engine.py"]

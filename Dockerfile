# Multi-stage Dockerfile for SovereignForge
# GPU-accelerated arbitrage detection system with MiCA compliance

# ================================
# Stage 1: Builder Stage
# ================================
FROM nvidia/cuda:12.1-devel-ubuntu22.04 AS builder

# Security hardening: Use non-root user
ENV USER=sovereignforge
ENV UID=1000
ENV GID=1000

# Install system dependencies with security updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        python3.10 \
        python3.10-dev \
        python3.10-venv \
        python3-pip \
        build-essential \
        git \
        curl \
        ca-certificates \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r -g $GID $USER && \
    useradd -r -u $UID -g $USER -s /bin/bash -m $USER

# Set working directory
WORKDIR /app

# Copy requirements for dependency installation
COPY requirements-gpu.txt requirements-gpu.txt

# Create virtual environment and install dependencies
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-gpu.txt

# ================================
# Stage 2: Runtime Stage
# ================================
FROM nvidia/cuda:12.1-runtime-ubuntu22.04 AS runtime

# Copy user and group from builder
COPY --from=builder /etc/group /etc/group
COPY --from=builder /etc/passwd /etc/passwd
COPY --from=builder /etc/shadow /etc/shadow

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Install runtime dependencies only
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        python3.10 \
        python3-pip \
        curl \
        ca-certificates \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create application directories
RUN mkdir -p /app /app/models /app/logs /app/data && \
    chown -R sovereignforge:sovereignforge /app

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=sovereignforge:sovereignforge . .

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
ENV CUDA_VISIBLE_DEVICES=0

# GPU memory management
ENV GPU_MEMORY_FRACTION=0.8
ENV GPU_MEMORY_LIMIT_MB=12288

# Security: Switch to non-root user
USER sovereignforge

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Expose ports
EXPOSE 8000 9090

# Default command
CMD ["python3", "src/main.py", "production"]
# SovereignForge Multi-Stage Docker Build with GPU Support
# MiCA Compliant Production Deployment with Security Hardening

# GPU Build stage
FROM nvidia/cuda:11.8-devel-ubuntu22.04 as gpu-builder

# Install system dependencies for GPU build
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies with GPU support
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY models/ ./models/

# Production stage with GPU runtime
FROM nvidia/cuda:11.8-runtime-ubuntu22.04 as production

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl \
    libssl3 \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

# Security hardening
RUN apt-get update && apt-get install -y \
    apparmor \
    apparmor-utils \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with minimal privileges
RUN groupadd -r sovereignforge && useradd --no-log-init -r -g sovereignforge -s /bin/bash sovereignforge

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=gpu-builder /root/.local /home/sovereignforge/.local
ENV PATH=/home/sovereignforge/.local/bin:$PATH

# Copy application code with secure permissions
COPY --chown=sovereignforge:sovereignforge src/ ./src/
COPY --chown=sovereignforge:sovereignforge models/ ./models/
COPY --chown=sovereignforge:sovereignforge config/ ./config/

# Create necessary directories with secure permissions
RUN mkdir -p /app/logs /app/data /app/secrets && \
    chown -R sovereignforge:sovereignforge /app && \
    chmod -R 755 /app && \
    chmod 700 /app/secrets

# GPU environment variables
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV CUDA_VISIBLE_DEVICES=0

# Security environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random

# MiCA compliance environment variables
ENV MICA_COMPLIANCE_ENABLED=true
ENV LOCAL_EXECUTION_ONLY=true
ENV NO_CUSTODY_MODE=true

# Switch to non-root user
USER sovereignforge

# Health check with GPU verification
HEALTHCHECK --interval=60s --timeout=30s --start-period=120s --retries=3 \
    CMD python3 -c "import torch; print('GPU available:', torch.cuda.is_available()); exit(0 if torch.cuda.is_available() else 1)"

# Expose port
EXPOSE 8000

# Default command with security flags
CMD ["python3", "-u", "-m", "src.live_arbitrage_pipeline"]

# Labels for security and compliance
LABEL org.opencontainers.image.title="SovereignForge"
LABEL org.opencontainers.image.description="MiCA Compliant Arbitrage Trading System"
LABEL org.opencontainers.image.vendor="SovereignForge"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.created="2024-01-01"
LABEL security.mica.compliant="true"
LABEL security.local.execution="true"
LABEL security.no.custody="true"

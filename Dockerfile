#--- START OF FULL, FINAL, AND CONFIRMED READY-TO-USE FILE: Dockerfile ---
# ================================
# Base Image: Official Playwright (Includes Python + Browsers)
# ================================
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# ================================
# Environment
# ================================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Aden

# ================================
# System Dependencies (Minimal extras needed)
# ================================
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    vim \
    tzdata \
    procps \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# ================================
# Timezone Configuration
# ================================
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ================================
# Working Directory
# ================================
WORKDIR /app

# ================================
# Python Dependencies
# ================================
# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ================================
# Copy Application
# ================================
COPY . /app

# Create directory for evidence
RUN mkdir -p /app/evidence

# ================================
# Healthcheck
# ================================
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ps aux | grep "[p]ython" || exit 1

# ================================
# Run
# ================================
CMD ["python", "-m", "src.main"]
#--- END OF FULL, FINAL, AND CONFIRMED READY-TO-USE FILE: Dockerfile ---
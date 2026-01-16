# Use a slim Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# The "Bypass Everything" Solution for MAC/TLS corruption errors
# 1. Force use of non-HTTPS mirrors to bypass TLS issues
# 2. Tell the package manager to ignore certificate checks
# 3. Use standard HTTP for mirrors
RUN sed -i 's|http://deb.debian.org|http://ftp.us.debian.org|g' /etc/apt/sources.list.d/debian.sources || true && \
    sed -i 's|https://|http://|g' /etc/apt/sources.list.d/debian.sources || true

# Run update with security checks disabled temporarily
RUN apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements-docker.txt .

# Install dependencies - skipping SSL verification here too if needed
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements-docker.txt

# Install Playwright browser
RUN playwright install chromium

# Copy the rest of the application
COPY . .

EXPOSE 8501

# Start the Hunter Mission Control
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]

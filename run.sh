pip install playwright fastapi[all]
playwright install chromium
apt-get update && \
    xargs -a packages.txt apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

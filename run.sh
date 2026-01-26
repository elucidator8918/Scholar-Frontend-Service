apt-get update && xargs -a packages.txt apt-get install -y --no-install-recommends
pip install playwright fastapi[all]
playwright install chromium

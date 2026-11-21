apt-get update && xargs -a packages.txt apt-get install -y --no-install-recommends
pip install scholarly "bibtexparser~=1.4" fastapi[all]

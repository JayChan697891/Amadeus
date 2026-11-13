set -eu
umask 077
export PYTHONDONTWRITEBYTECODE=1 PIP_NO_INDEX=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
/root/jobs-env/bin/python -I -B - <<'PY'
from pathlib import Path
import hashlib,json,tarfile,zipfile
base=Path('/root/amadeus-sdist-repair-9fb36a1')
base.mkdir(mode=0o700)
with zipfile.ZipFile('/root/amadeus-sdist-repair-9fb36a1.zip') as archive:
    assert all((base/n).resolve().is_relative_to(base) for n in archive.namelist())
    archive.extractall(base)
config=json.loads((base/'identity.json').read_text())
source=base/'agentsync_local-0.3.0a109.tar.gz'
assert hashlib.sha256(source.read_bytes()).hexdigest()==config['sdist_sha256']
with tarfile.open(source) as archive:
    for member in archive.getmembers():
        assert member.isdir() or member.isfile()
        assert (base/'unpacked'/member.name).resolve().is_relative_to(base/'unpacked')
    archive.extractall(base/'unpacked',filter='data')
next((base/'unpacked').iterdir()).rename(base/'source')
PY
cd /root/amadeus-sdist-repair-9fb36a1
mkdir home tmp
export HOME="$PWD/home" CODEX_HOME="$PWD/home" TMPDIR="$PWD/tmp" PIP_CACHE_DIR="$PWD/pip-cache"
/root/jobs-env/bin/python -m venv venv
venv/bin/python -m pip install --no-index --no-cache-dir --find-links /root/intent-wheelhouse ./agentsync_local-0.3.0a109.tar.gz pytest==9.1.1 pytest-asyncio==1.4.0 httpx==0.28.1 > install.log 2>&1
venv/bin/python -m pip check > pip-check.log
venv/bin/python -I -B driver.py > driver.log 2>&1
cat driver.log

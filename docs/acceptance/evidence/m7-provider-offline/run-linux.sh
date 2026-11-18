set -eu
umask 077
/root/amadeus-sdist-repair-9fb36a1/venv/bin/python -I -B - <<'PY'
from pathlib import Path
import zipfile
base=Path('/root/amadeus-providers-2af7ccc')
base.mkdir(mode=0o700)
for archive_path,destination in ((Path('/root/amadeus-providers-2af7ccc.zip'),base),(base/'source.zip',base/'source')):
    with zipfile.ZipFile(archive_path) as archive:
        assert all((destination/n).resolve().is_relative_to(destination) for n in archive.namelist())
        archive.extractall(destination)
PY
/root/amadeus-sdist-repair-9fb36a1/venv/bin/python -I -B /root/amadeus-providers-2af7ccc/driver.py

set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import hashlib,zipfile
from pathlib import Path
p=Path('/root/amadeus-continuation-bridge-input-20261116.zip')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='8e624d7498323bee9b6dd6ffdba66c19d67df7d94282436bc450dfdde91a0783'
d=Path('/root/amadeus-continuation-bridge-20261116')
d.mkdir(mode=0o700)
with zipfile.ZipFile(p) as a:
 assert set(a.namelist())=={'source.zip','inputs.json','runtime-members.json','run.py'}
 for name in a.namelist():
  with (d/name).open('xb') as f:f.write(a.read(name))
PY
exec /root/jobs-env/bin/python -I -B /root/amadeus-continuation-bridge-20261116/run.py

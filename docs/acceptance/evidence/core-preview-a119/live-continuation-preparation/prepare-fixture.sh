set -eu
umask 077
BASE=/root/amadeus-interrupted-a119-solution-20261116
chmod 600 "$BASE/prepare.py" "$BASE/private_capture.py" "$BASE/runtime-members.json"
/root/amadeus-m119l/w/bin/python -I -B "$BASE/prepare.py" prepare
/root/amadeus-m119l/w/bin/python -I -B - <<'PY'
import json, subprocess
from pathlib import Path
base = Path('/root/amadeus-interrupted-a119-solution-20261116')
plan = json.loads((base / 'plan.json').read_bytes())
subprocess.run(['/root/amadeus-m119l/w/bin/python', '-I', '-B', str(base / 'prepare.py'), 'ready', plan['producer_plan']['plan_sha256']], check=True)
PY

set -eu
/root/amadeus-m119l/w/bin/python -I -B - <<'PY'
import hashlib, json, os, subprocess
from datetime import UTC, datetime
from pathlib import Path
import agentsync
workers = []
for p in Path('/proc').iterdir():
    if not p.name.isdecimal() or int(p.name) == os.getpid():
        continue
    try:
        name = (p / 'exe').resolve(strict=True).name
        if name.startswith(('python', 'codex')):
            workers.append({'pid': int(p.name), 'name': name})
    except (FileNotFoundError, PermissionError):
        pass
containers = subprocess.run(['docker', 'ps', '-aq'], capture_output=True, check=True, text=True).stdout.splitlines()
assert not workers and not containers
base = Path('/root/amadeus-interrupted-a119-solution-20261116')
assert not base.exists()
image = 'sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'
image_data = json.loads(subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, check=True).stdout)
assert len(image_data) == 1 and image_data[0]['Id'] == image
old = Path('/root/amadeus-interrupted-a117-r2-20261116')
preserved = {}
for p in sorted(old.rglob('*')):
    if p.is_file() and not p.is_symlink():
        preserved[p.relative_to(old).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'at': datetime.now(UTC).isoformat(), 'version': agentsync.__version__, 'origin': str(Path(agentsync.__file__).resolve()), 'workers': workers, 'containers': containers, 'image': image, 'fresh_fixture_absent': True, 'historical_r2_files': len(preserved), 'historical_r2_map_sha256': hashlib.sha256(json.dumps(preserved, sort_keys=True).encode()).hexdigest(), 'model_calls': 0, 'auth_copies': 0}, sort_keys=True))
PY

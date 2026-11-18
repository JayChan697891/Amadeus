set -eu
/root/amadeus-m119l/w/bin/python -I -B - <<'PY'
from pathlib import Path
b = Path('/root/amadeus-interrupted-a119-solution-20261116')
for name in ('interrupt_parent.py', 'cleanup.py', 'verify.py', 'live.py', 'run-stage.py', 'receiver-decision.py', 'live-authorization.template.json', 'bound-helpers.json'):
    assert not (b / name).exists(), name
assert not (b / 'live-authorization.json').exists()
assert not any((b / 'private-home').iterdir())
PY

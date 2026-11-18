set -eu
umask 077
/root/amadeus-m119l/w/bin/python -I -B - <<'PY'
import hashlib, json, os
from datetime import UTC, datetime
from pathlib import Path
b = Path('/root/amadeus-interrupted-a119-solution-20261116')
inputs = json.loads((b / 'bound-helpers.json').read_bytes())
for name, expected in inputs.items():
    p = b / name
    p.chmod(0o600)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, name
    if name.endswith('.py'):
        compile(p.read_bytes(), str(p), 'exec')
grant = json.loads((b / 'live-authorization.template.json').read_bytes())
assert grant['expires_at'] is grant['owner_confirmed_zero_credits_and_auto_recharge_off'] is None
for name, expected in grant['files'].items():
    assert hashlib.sha256((b / name).read_bytes()).hexdigest() == expected, name
assert not any((b / 'private-home').iterdir())
for name in ('live-authorization.json', 'producer-entry.json', 'receiver-entry.json', 'stage-entry.json', 'execution-entry.json', 'completion-entry.json'):
    assert not (b / name).exists(), name
assert str(b / 'private-home') not in Path('/proc/mounts').read_text()
old = Path('/root/amadeus-interrupted-a117-r2-20261116')
preserved = {p.relative_to(old).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(old.rglob('*')) if p.is_file() and not p.is_symlink()}
old_sha = hashlib.sha256(json.dumps(preserved, sort_keys=True).encode()).hexdigest()
assert len(preserved) == 115 and old_sha == '36f67436b52ab81634f3033e23adf901f069f087aa04307b9e82e5dcb2c69852'
print(json.dumps({'at': datetime.now(UTC).isoformat(), 'helper_count': len(inputs), 'bound_input_count': len(grant['files']), 'all_hashes_match': True, 'historical_r2_unchanged': True, 'real_authorization_absent': True, 'private_home_empty_unmounted': True, 'model_calls': 0, 'candidate_executions': 0, 'auth_copies': 0}))
PY

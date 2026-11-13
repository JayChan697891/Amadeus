"""Check the actual installed archive, SDK, console scripts and license inventory."""
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
environment = BASE / ('installed' if sys.platform == 'win32' else 'venv')
# Linux venv executables are symlinks to the base interpreter; prefix identifies the venv.
assert Path(sys.prefix).resolve() == environment.resolve()
for name in tuple(os.environ):
    upper = name.upper()
    if upper.startswith(('AGENTSYNC_', 'OPENAI_', 'ANTHROPIC_', 'CLAUDE_', 'CURSOR_', 'PYTEST_', 'GIT_')) or upper in {'CODEX_HOME','CODEX_API_KEY','PYTHONPATH','PYTHONHOME'}:
        os.environ.pop(name, None)
scratch = BASE / 'install-smoke'
scratch.mkdir(mode=0o700)
for name in ('home', 'tmp', 'project'):
    (scratch/name).mkdir(mode=0o700)
os.environ.update(HOME=str(scratch/'home'), USERPROFILE=str(scratch/'home'), CODEX_HOME=str(scratch/'home'),
    TEMP=str(scratch/'tmp'), TMP=str(scratch/'tmp'), TMPDIR=str(scratch/'tmp'),
    PYTHONDONTWRITEBYTECODE='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
import agentsync
from agentsync.sdk import AgentSyncClient
config = json.loads((BASE/'identity.json').read_text())
archive = BASE/'agentsync_local-0.3.0a109.tar.gz'
expected = config['sdist_sha256']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
site = Path(agentsync.__file__).resolve().parent.parent
assert site.is_relative_to(environment.resolve())
distribution = importlib.metadata.distribution('agentsync-local')
assert distribution.version == '0.3.0a109'
direct = json.loads(distribution.read_text('direct_url.json'))
assert direct['url'] == archive.as_uri()
assert (direct['archive_info'].get('hashes', {}).get('sha256') or
    direct['archive_info'].get('hash', '').removeprefix('sha256=')) == expected
assert not direct.get('dir_info', {}).get('editable', False)
for name, value in config['runtime_members'].items():
    assert hashlib.sha256((site/name).read_bytes()).hexdigest() == value
client = AgentSyncClient(scratch/'sdk-data')
response = client.call('create_project', name='Dedicated installed SDK smoke', root_path=str(scratch/'project'))
assert response['ok'] is True
del response
spec = importlib.util.spec_from_file_location('acceptance_collector', BASE/'source/tools/release_acceptance.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
artifact = {'path': archive.name, 'sha256': expected, 'size': archive.stat().st_size}
console = collector._installed_console_smoke('sdist', sys.executable, BASE, scratch, artifact)
license_result = collector._installed_license_inventory('sdist', sys.executable, BASE/'source',
    BASE, scratch, distribution.version, artifact, {'id': 'sdist_origin_sdk'})
record = {'product_sha': config['product_sha'], 'test_source_sha': config['test_source_sha'],
    'sdist_sha256': expected, 'platform': sys.platform, 'version': distribution.version,
    'installed_origin': str(site/'agentsync'), 'direct_archive': direct,
    'runtime_members_matched': len(config['runtime_members']), 'sdk_smoke': 'pass',
    'console_smoke': console, 'license_inventory': license_result, 'model_calls': 0,
    'formal_release': 'BLOCKED'}
with (BASE/'installation-observation.json').open('x', encoding='utf-8') as out:
    json.dump(record, out, indent=2)
    out.write('\n')
assert console['status'] == 'pass'
print(json.dumps({'sdk': 'pass', 'console': console['status'], 'license_inventory': license_result['status'],
    'license_review': 'pending', 'model_calls': 0}))

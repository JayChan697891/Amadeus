"""Run one frozen continuation bridge selection in the existing local Linux runtime."""

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

BASE = Path('/root/amadeus-continuation-bridge-20261116')
SOURCE = BASE / 'source'
RUN = BASE / 'results'
PYTHON = '/root/amadeus-m118l/w/bin/python'
SITE = Path('/root/amadeus-m118l/w/lib/python3.14/site-packages')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (RUN / name).open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def main():
    manifest = json.loads((BASE / 'inputs.json').read_bytes())
    members = json.loads((BASE / 'runtime-members.json').read_bytes())
    assert sha(BASE / 'source.zip') == manifest['archive_sha256']
    assert sha(Path(__file__)) == manifest['runner_sha256']
    assert len(members) == 97
    assert all(sha(SITE / name) == value for name, value in members.items())
    SOURCE.mkdir()
    RUN.mkdir()
    (BASE / 'home').mkdir(mode=0o700)
    (BASE / 'tmp').mkdir(mode=0o700)
    (RUN / 'docker').mkdir()
    with zipfile.ZipFile(BASE / 'source.zip') as archive:
        assert set(archive.namelist()) == manifest['files'].keys()
        for name in archive.namelist():
            target = SOURCE / name
            assert target.resolve().is_relative_to(SOURCE)
            content = archive.read(name)
            assert hashlib.sha256(content).hexdigest() == manifest['files'][name]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(content)
    environment = os.environ.copy()
    for name in ('AGENTSYNC_DATA_DIR', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
        environment.pop(name, None)
    delta = {
        'HOME': str(BASE / 'home'), 'TMPDIR': str(BASE / 'tmp'),
        'PYTHONPATH': str(SOURCE / 'src'), 'PYTHONDONTWRITEBYTECODE': '1',
        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
        'AGENTSYNC_DOCKER_TEST_IMAGE': manifest['image_id'],
        'AGENTSYNC_REQUIRE_DOCKER_TESTS': '1',
        'AGENTSYNC_PROPOSAL_PIPELINE_EVIDENCE_DIR': str(RUN / 'docker'),
    }
    environment.update(delta)
    origin = subprocess.run(
        [PYTHON, '-s', '-B', '-c', 'import agentsync; print(agentsync.__file__)'],
        env=environment, cwd=SOURCE, text=True, capture_output=True, check=True,
    )
    assert Path(origin.stdout.strip()) == SOURCE / 'src/agentsync/__init__.py'
    command = [PYTHON, '-s', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               '--basetemp', str(BASE / 'tmp/pytest'),
               '--junitxml=' + str(RUN / 'junit.xml'), *manifest['selection']]
    started = datetime.now(UTC).isoformat()
    with (RUN / 'pytest.log').open('xb') as log:
        process = subprocess.run(command, cwd=SOURCE, env=environment, stdout=log,
                                 stderr=subprocess.STDOUT, check=False)
    source_ok = all(sha(SOURCE / name) == value for name, value in manifest['files'].items())
    installed_ok = all(sha(SITE / name) == value for name, value in members.items())
    save('process.json', {
        'started_at': started, 'finished_at': datetime.now(UTC).isoformat(),
        'command': command, 'cwd': str(SOURCE), 'environment_delta': delta,
        'exit_code': process.returncode, 'commit': manifest['commit'],
        'import_origin': origin.stdout.strip(), 'source_files': len(manifest['files']),
        'source_unchanged': source_ok, 'installed_members': 97,
        'installed_members_unchanged': installed_ok, 'model_calls': 0,
    })
    print((RUN / 'process.json').read_text(), flush=True)
    assert source_ok and installed_ok
    raise SystemExit(process.returncode)


if __name__ == '__main__':
    main()

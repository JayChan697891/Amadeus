set -eu
umask 077
/root/amadeus-m119l/w/bin/python -I -B - <<'PY'
import hashlib, json, os, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
from agentsync.core.service import Core
from agentsync.storage.database import connect
base = Path('/root/amadeus-interrupted-a119-solution-20261116')
sys.path.insert(0, str(base))
import cleanup, live, prepare, verify
live.prep, live.cleanup = prepare, cleanup
with cleanup.stage_lock(allow_closing=True):
    _, grant = cleanup.validate_authorization(allow_expired=True)
    verify.require_closed(cleanup, grant)
    core, state = live.core_state()
    before = live.task_graph(core, state)
    assert before == live.read('completion-postcheck.json')['tasks']
    completed = live.read('completion-result.json')
    receiver = completed['task_id']
    assert live.read('verification-replay.json') == {'task_id': receiver, 'new_executions': 0, 'model_calls': 0}
    dependent = state['dependent']['id']
    assert before[dependent]['status'] == 'pending' and before[dependent]['dependencies'] == [receiver]
    assert before[receiver]['status'] == 'completed' and before[receiver]['task_verification'] == 'verified'
    request = {'task_id': dependent, 'expected_version': before[dependent]['version'], 'request_id': 'claim-live-json-lines-dependent'}
    cleanup.save('dependent-claim-entry.json', request)
    claimed = core.execute('claim_task', {**prepare.auth(state, 'producer'), **request})
    cleanup.save('dependent-claim-private.json', claimed)
    assert claimed['status'] == 'claimed'
    fresh = Core(core.data_dir)
    after = live.task_graph(fresh, state)
    assert after == before | {dependent: before[dependent] | {'status': 'claimed', 'version': before[dependent]['version'] + 1}}
    job_id = live.read('execution-plan.json')['job']['id']
    with connect(fresh.db_path) as db:
        count = db.execute('SELECT count(*) FROM candidate_executions WHERE project_id=? AND job_id=?', (state['owner']['project_id'], job_id)).fetchone()[0]
    assert count == 1
    prepare.require_fixtures(state)
    prepare.runtime()
    old = Path('/root/amadeus-interrupted-a117-r2-20261116')
    preserved = {p.relative_to(old).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(old.rglob('*')) if p.is_file() and not p.is_symlink()}
    assert len(preserved) == 115 and hashlib.sha256(json.dumps(preserved, sort_keys=True).encode()).hexdigest() == '36f67436b52ab81634f3033e23adf901f069f087aa04307b9e82e5dcb2c69852'
    containers = subprocess.run(['docker', 'ps', '-aq'], capture_output=True, check=True, text=True).stdout.splitlines()
    workers = []
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal() or int(p.name) == os.getpid(): continue
        try:
            name = (p / 'exe').resolve(strict=True).name
            if name.startswith(('python', 'codex')): workers.append({'pid': int(p.name), 'name': name})
        except (FileNotFoundError, PermissionError): pass
    assert not containers and not workers
    result = {'at': datetime.now(UTC).isoformat(), 'project_id': state['owner']['project_id'], 'tasks': after, 'dependent_claim': {'task_id': dependent, 'status': claimed['status'], 'version': after[dependent]['version']}, 'candidate_execution_count': count, 'further_model_calls': 0, 'runtime_members_unchanged': 97, 'historical_r2_files_unchanged': 115, 'containers': containers, 'workers': workers, 'temporary_auth_absent': True, 'formal_release': 'BLOCKED'}
    live.write('final-postcheck.json', result, state)
    print(json.dumps(result), flush=True)
PY

"""Strict local operator bridge for the four exact reviewed decisions; no credential access."""
import hashlib
import json
import re
import stat
import sys
import time
from pathlib import Path

import paramiko

BASE = Path('D:/agentsync-debug/m7-continuous-monotonic-live-20261113')
REMOTE = '/root/amadeus-continuous-monotonic-live-20261113'
STAGES = {'staging', 'execution', 'completion', 'receiver'}
SAFE = {'plan.json', 'readiness.json', 'credential-home.json', 'attempt.json',
    'auth-route-producer.json', 'auth-route-receiver.json', 'producer-proposal.json',
    'producer-capture.json', 'receiver-capture.json', 'job.json', 'execution.json',
    'dispatch-observation.json', 'result.json', 'auth-cleanup.json'}
SAFE |= {stage + suffix for stage in STAGES for suffix in ('-request.json', '-accepted.json')}
FORBIDDEN = {'admin_token', 'session_token', 'lease_token', 'access_token', 'refresh_token',
    'id_token', 'OPENAI_API_KEY'}


def safe(value):
    if isinstance(value, dict):
        assert not set(value) & FORBIDDEN
        for child in value.values():
            safe(child)
    elif isinstance(value, list):
        for child in value:
            safe(child)


def read(sftp, name):
    assert name in SAFE
    path = REMOTE + '/' + name
    info = sftp.lstat(path)
    assert stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600
    assert 0 < info.st_size <= 65536
    with sftp.open(path, 'rb') as stream:
        opened = stream.stat()
        assert stat.S_ISREG(opened.st_mode) and opened.st_size == info.st_size
        assert opened.st_uid == 0 and stat.S_IMODE(opened.st_mode) == 0o600
        data = stream.read(65537)
    assert len(data) == info.st_size
    value = json.loads(data)
    safe(value)
    return data, value


def retain(name, data):
    path = BASE / name
    if path.exists():
        assert path.read_bytes() == data
    else:
        with path.open('xb') as out:
            out.write(data)


def main():
    args = sys.argv[1:]
    assert args
    client = paramiko.SSHClient()
    client.load_host_keys('D:/agentsync-debug/vm/known_hosts')
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect('127.0.0.1', port=22222, username='root',
        key_filename='D:/agentsync-debug/vm/debug_ed25519', look_for_keys=False,
        allow_agent=False, timeout=10, auth_timeout=15)
    try:
        with client.open_sftp() as sftp:
            if args == ['status']:
                names = set(sftp.listdir(REMOTE))
                print(json.dumps({'pending': sorted(stage for stage in STAGES
                    if stage + '-request.json' in names and stage + '-accepted.json' not in names),
                    'result_recorded': 'result.json' in names,
                    'dispatch_recorded': 'dispatch-observation.json' in names,
                    'auth_cleanup_recorded': 'auth-cleanup.json' in names}))
            elif len(args) == 2 and args[0] == 'inspect' and args[1] in STAGES:
                name = args[1] + '-request.json'
                data, request = read(sftp, name)
                retain(name, data)
                print(json.dumps(request, indent=2))
            elif len(args) == 3 and args[0] == 'approve' and args[1] in STAGES:
                stage, expected = args[1:]
                assert re.fullmatch('[0-9a-f]{64}', expected)
                name = stage + '-request.json'
                local = (BASE / name).read_bytes()
                data, request = read(sftp, name)
                assert data == local and request['stage'] == stage
                assert request['decision_sha256'] == expected and time.time() < request['expires_at']
                decision = {'stage': stage, 'decision_sha256': expected,
                    'request_sha256': hashlib.sha256(data).hexdigest(),
                    'expires_at': min(time.time() + 60, request['expires_at'])}
                encoded = (json.dumps(decision, indent=2) + '\n').encode()
                remote = REMOTE + '/' + stage + '-decision.json'
                with sftp.open(remote, 'x+b') as out:
                    sftp.chmod(remote, 0o600)
                    out.write(encoded)
                    out.flush()
                retain(stage + '-decision.json', encoded)
                print(json.dumps({'exact_decision_written': stage, 'decision_sha256': expected}))
            elif len(args) >= 2 and args[0] == 'fetch':
                assert len(args[1:]) == len(set(args[1:]))
                for name in args[1:]:
                    data, _ = read(sftp, name)
                    retain(name, data)
                    print(json.dumps({'saved': name, 'bytes': len(data)}))
            else:
                raise ValueError('Invalid bounded operator operation')
    finally:
        client.close()


if __name__ == '__main__':
    main()

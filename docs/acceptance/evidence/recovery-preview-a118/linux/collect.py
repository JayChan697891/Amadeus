import hashlib
import json
import shlex
import stat
from datetime import UTC, datetime
from pathlib import Path

import paramiko

BASE = Path(__file__).resolve().parent
OUT = BASE / 'collected'
GUEST = '/root/amadeus-m118l'
vm = Path('D:/agentsync-debug/vm')
client = paramiko.SSHClient()
client.load_host_keys(str(vm / 'known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('127.0.0.1', port=22222, username='root', key_filename=str(vm / 'debug_ed25519'), look_for_keys=False, allow_agent=False, timeout=15)
probe = '''
import hashlib,json,os
from pathlib import Path
b=Path('/root/amadeus-m118l')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((b/'source-manifest.json').read_bytes())
members=json.loads((b/'runtime-members.json').read_bytes())
assert len(manifest)==2899 and len(members)==97
assert all(sha(b/'s'/n)==v['sha256'] for n,v in manifest.items())
assert {p.relative_to(b/'s').as_posix() for p in (b/'s').rglob('*') if p.is_file()}==set(manifest)
for env in ('w','d'):
 site=b/env/'lib/python3.14/site-packages'
 assert all(sha(site/n)==h for n,h in members.items())
workers=[]
for p in Path('/proc').iterdir():
 if not p.name.isdecimal() or int(p.name)==os.getpid():continue
 try:
  name=(p/'exe').resolve(strict=True).name
  if name.startswith(('python','codex')):workers.append({'pid':int(p.name),'name':name})
 except (FileNotFoundError,PermissionError):pass
assert not workers
files={p.relative_to(b).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (b/'run').rglob('*') if p.is_file()}
print(json.dumps({'files':files,'source_files':len(manifest),'runtime_members_each':len(members),'workers':workers,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''
try:
    _, stdout, stderr = client.exec_command(shlex.join(['/root/jobs-env/bin/python', '-I', '-B', '-c', probe]), timeout=60)
    body, error = stdout.read(1024*1024), stderr.read(65536)
    code = stdout.channel.recv_exit_status()
    assert code == 0 and not error, (code, error.decode(errors='replace'))
    observed = json.loads(body)
    assert sum(row['bytes'] for row in observed['files'].values()) < 16*1024*1024
    OUT.mkdir()
    with client.open_sftp() as sftp:
        for name, row in observed['files'].items():
            assert name.startswith('run/') and '..' not in Path(name).parts
            remote = GUEST + '/' + name
            assert stat.S_ISREG(sftp.lstat(remote).st_mode)
            with sftp.open(remote, 'rb') as stream:
                data = stream.read()
            assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
            target = OUT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
    observed.update(observed_at=datetime.now(UTC).isoformat(), native_session=45407, native_exit_code=0, native_terminal_chunk='1c73f8')
    with (BASE/'collection.json').open('x',encoding='utf-8') as stream:
        json.dump(observed,stream,indent=2)
    result=json.loads((OUT/'run/result.json').read_bytes())
    print(json.dumps({k:result[k] for k in ('status','started_at','finished_at','junit','input_hashes_unchanged','source_copy_unchanged')}))
    print(json.dumps({'files':len(observed['files']),'bytes':sum(v['bytes'] for v in observed['files'].values()),'workers':observed['workers']}))
finally:
    client.close()

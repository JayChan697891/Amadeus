set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import hashlib, io, json, os, pathlib, subprocess, tarfile
from datetime import datetime, timezone
base=pathlib.Path('/root/amadeus-m120l'); run=base/'run'
r=json.loads((run/'result.json').read_bytes())
assert r['status']=='pass' and len(r['checks'])==16
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
active=[]
for p in pathlib.Path('/proc').iterdir():
    if not p.name.isdecimal() or int(p.name)==os.getpid():continue
    try:
        comm=(p/'comm').read_text().strip(); cmd=(p/'cmdline').read_bytes()
        if ('python' in comm or 'codex' in comm) and any(tag in cmd for tag in (b'/root/amadeus-',b'/root/agentsync-')):active.append({'pid':int(p.name),'name':comm})
    except OSError:pass
assert not active
containers=subprocess.check_output(['docker','ps','-q'],text=True).splitlines()
assert not containers
members=json.loads((base/'runtime-members.json').read_bytes())
installed={}
for kind,folder in (('wheel','w'),('sdist','d')):
    site=base/folder/'lib/python3.14/site-packages'
    actual={p.relative_to(site).as_posix():sha(p) for p in (site/'agentsync').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    assert actual==members and len(actual)==97
    installed[kind]=len(actual)
record={'observed_at':datetime.now(timezone.utc).isoformat(),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'active_project_workers':active,'running_containers':containers,'installed_members_verified':installed,'credential_copies':0,'model_calls':0,'candidate_executions':0,'formal_release':'BLOCKED'}
with (run/'postcheck.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2);f.write('\n')
files=[p for p in sorted(run.rglob('*')) if p.is_file()]+[base/'linux-run-preview.py']
assert all(not p.is_symlink() for p in files)
manifest={('run/'+p.relative_to(run).as_posix() if p.is_relative_to(run) else p.name):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files}
archive=base/'public-linux-evidence.tar.gz'
with archive.open('xb') as stream, tarfile.open(fileobj=stream,mode='w:gz') as tar:
    for p in files:
        name='run/'+p.relative_to(run).as_posix() if p.is_relative_to(run) else p.name
        tar.add(p,arcname=name,recursive=False)
    data=json.dumps(manifest,indent=2).encode(); item=tarfile.TarInfo('file-inventory.json');item.size=len(data);tar.addfile(item,io.BytesIO(data))
print(json.dumps({'archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files),'checks':len(r['checks']),'junit':r['junit'],'postcheck':record},indent=2))
PY
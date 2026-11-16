set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import hashlib,json,os,stat,subprocess,xml.etree.ElementTree as ET,zipfile
from datetime import UTC,datetime
from pathlib import Path
base=Path('/root/amadeus-m119l');run=base/'run';result=json.loads((run/'result.json').read_bytes())
assert result['status']=='pass' and len(result['checks'])==16
assert all(row['status']=='pass' and row['exit_code']==0 for row in result['checks'])
for name,digest in result['native_receipt_sha256'].items():assert hashlib.sha256((run/'logs'/name).read_bytes()).hexdigest()==digest
manifest=json.loads((base/'source-manifest.json').read_bytes());members=json.loads((base/'runtime-members.json').read_bytes())
assert len(manifest)==3090 and all(hashlib.sha256((base/'s'/name).read_bytes()).hexdigest()==row['sha256'] for name,row in manifest.items())
identities=[];containers=[]
for kind,env in [('wheel','w'),('sdist','d')]:
 assert all(hashlib.sha256((base/env/'lib/python3.14/site-packages'/name).read_bytes()).hexdigest()==h for name,h in members.items())
 rows=ET.parse(run/result['junit'][kind]['path']).findall('.//testcase')
 assert len(rows)==16 and all(not list(row) for row in rows)
 identities.append({(r.get('classname'),r.get('name')) for r in rows})
 p=run/result['docker_proofs'][kind]['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==result['docker_proofs'][kind]['sha256']
 proof=json.loads(p.read_bytes());execution=proof['execution']['execution']['result']
 assert execution['backend']=='local-linux-docker' and execution['passed_case_count']==2 and len(execution['isolation']['checks'])==19 and all(execution['isolation']['checks'].values()) and execution['cleanup_confirmed']
 assert proof['source_task_status']=='failed' and proof['receiver_task_status']=='completed' and proof['receiver_task_verification']=='verified'
 containers.append(execution['container_id'])
assert identities[0]==identities[1]
remaining=subprocess.run(['docker','ps','-aq'],capture_output=True,text=True,check=True).stdout.splitlines()
assert not set(containers)&set(remaining)
workers=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:raw=p.read_bytes()
 except (FileNotFoundError,ProcessLookupError,PermissionError):continue
 if str(base).encode() in raw and int(p.parent.name)!=os.getpid():workers.append(p.parent.name)
assert not workers
post={'recorded_at':datetime.now(UTC).isoformat(),'source_files_unchanged':3090,'installed_members_per_environment_unchanged':len(members),'checks':16,'cases_per_install':16,'docker_cases_per_install':2,'isolation_checks_per_install':19,'fixture_workers':workers,'remaining_container_count':len(remaining),'owned_containers_absent':True,'model_calls':0}
with (run/'postcheck.json').open('x',encoding='utf-8') as stream:json.dump(post,stream,indent=2)
files={}
for path in sorted(run.rglob('*')):
 if path.is_dir():continue
 assert stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink() and path.suffix in ('.json','.log','.xml')
 name=path.relative_to(base).as_posix();files[name]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
with (base/'collection.json').open('x',encoding='utf-8') as stream:json.dump(files,stream,indent=2)
with zipfile.ZipFile(base/'public-results.zip','x',zipfile.ZIP_DEFLATED) as archive:
 for name in list(files)+['collection.json']:archive.write(base/name,name)
print(json.dumps({'postcheck':post,'files':len(files),'bytes':sum(x['bytes'] for x in files.values()),'zip_sha256':hashlib.sha256((base/'public-results.zip').read_bytes()).hexdigest()}))
PY

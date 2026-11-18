set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import hashlib,json,os,subprocess,zipfile
from datetime import UTC,datetime
from pathlib import Path
base=Path('/root/amadeus-continuation-bridge-20261116')
inputs=json.loads((base/'inputs.json').read_bytes())
assert all(hashlib.sha256((base/'source'/name).read_bytes()).hexdigest()==value for name,value in inputs['files'].items())
result=json.loads((base/'results/docker/continuation-verified.json').read_bytes())
actual=result['execution']['execution']['result']
assert result['same_core'] and result['receiver_task_status']=='completed' and result['receiver_task_verification']=='verified'
assert result['source_task_status']=='failed' and result['publication_verification']=='unverified'
assert actual['backend']=='local-linux-docker' and actual['passed_case_count']==2 and actual['cleanup_confirmed']
assert all(actual['isolation']['checks'].values())
check=subprocess.run(['docker','ps','-aq'],capture_output=True,text=True,check=True,timeout=20)
assert actual['container_id'] not in check.stdout.splitlines()
workers=[]
for path in Path('/proc').glob('[0-9]*/cmdline'):
 try:raw=path.read_bytes()
 except (FileNotFoundError,ProcessLookupError,PermissionError):continue
 if str(base).encode() in raw and int(path.parent.name)!=os.getpid():workers.append(path.parent.name)
assert not workers,workers
inspection={'checked_at':datetime.now(UTC).isoformat(),'source_files_unchanged':len(inputs['files']),'owned_container_absent':True,'remaining_container_count':len(check.stdout.splitlines()),'fixture_process_ids':workers,'docker_cases_passed':actual['passed_case_count'],'isolation_checks_passed':len(actual['isolation']['checks']),'model_calls':0}
(base/'results/postcheck.json').write_text(json.dumps(inspection,indent=2)+'\n')
files=['results/process.json','results/junit.xml','results/pytest.log','results/docker/continuation-verified.json','results/postcheck.json']
manifest={name:{'bytes':(base/name).stat().st_size,'sha256':hashlib.sha256((base/name).read_bytes()).hexdigest()} for name in files}
(base/'collection.json').write_text(json.dumps(manifest,indent=2)+'\n')
with zipfile.ZipFile(base/'public-results.zip','x',zipfile.ZIP_DEFLATED) as archive:
 for name in files+['collection.json']:archive.write(base/name,name)
print(json.dumps({'inspection':inspection,'files':manifest,'zip_sha256':hashlib.sha256((base/'public-results.zip').read_bytes()).hexdigest()}))
PY

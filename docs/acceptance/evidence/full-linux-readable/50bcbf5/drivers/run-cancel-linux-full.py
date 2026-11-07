from pathlib import Path
import hashlib,json,subprocess,tarfile,tempfile,uuid
repo=Path('F:/syuc/agentsync-execution-intent')
out=Path(tempfile.mkdtemp(prefix='cancel-linux-full-',dir='D:/agentsync-debug'))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip()
guest='/root/agentsync-cancel-full-'+uuid.uuid4().hex
archive=out/'source.tar'
subprocess.run(['git','archive','--format=tar','--output',str(archive),commit],cwd=repo,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={}
with tarfile.open(archive) as stream:
 for m in stream:
  if m.isfile():manifest[m.name]=hashlib.sha256(stream.extractfile(m).read()).hexdigest()
config={'commit':commit,'guest':guest,'manifest':manifest,'archive_sha256':sha(archive)}
(out/'config.json').write_text(json.dumps(config,indent=2))
body=r"""
import hashlib,importlib,json,os,pathlib,signal,sqlite3,subprocess,sys,tarfile,time,xml.etree.ElementTree as ET
root=pathlib.Path(config['guest']);archive=pathlib.Path(config['guest']+'.tar')
assert hashlib.sha256(archive.read_bytes()).hexdigest()==config['archive_sha256'] and not root.exists()
root.mkdir();source=root/'source';source.mkdir();evidence=root/'evidence';evidence.mkdir()
with tarfile.open(archive) as stream:
 for m in stream:
  p=pathlib.PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts
  target=source/m.name;assert target.resolve().is_relative_to(source.resolve())
  if m.isdir():target.mkdir(parents=True,exist_ok=True);continue
  assert m.isfile();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stream.extractfile(m).read())
assert all(hashlib.sha256((source/n).read_bytes()).hexdigest()==h for n,h in config['manifest'].items())
for n in ['home','tmpbase']:(root/n).mkdir()
env={'PATH':'/root/jobs-env/bin:/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(root/'home'),'TMPDIR':str(root/'tmpbase'),'PYTHONPATH':str(source/'src'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PYTHONUNBUFFERED':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PIP_NO_INDEX':'1','PIP_CONFIG_FILE':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
image='sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'
for name,key in [('docker-evidence','AGENTSYNC_VERIFIER_EVIDENCE_DIR'),('owner-evidence','AGENTSYNC_OWNER_EXECUTOR_EVIDENCE_DIR'),('reconciliation-evidence','AGENTSYNC_RECONCILIATION_EVIDENCE_DIR'),('candidate-evidence','AGENTSYNC_CANDIDATE_EXECUTOR_EVIDENCE_DIR'),('task-completion-evidence','AGENTSYNC_TASK_COMPLETION_EVIDENCE_DIR')]:
 (evidence/name).mkdir();env[key]=str(evidence/name)
env.update(AGENTSYNC_DOCKER_TEST_IMAGE=image,AGENTSYNC_REQUIRE_DOCKER_TESTS='1')
probe=subprocess.run(['docker','image','inspect',image],env=env,capture_output=True,timeout=15,check=True)
image_info=json.loads(probe.stdout)[0];assert image_info['Id']==image
(evidence/'image.json').write_text(json.dumps({'Id':image_info['Id'],'RepoDigests':image_info.get('RepoDigests',[]),'network_pull':'NOT RUN'},indent=2))
wrapper=root/'run.py'
wrapper_body='''import hashlib,importlib,json,pathlib,sys
sys.dont_write_bytecode=True
source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);sys.path.insert(0,str(source/'src'))
def verify():
 observed={}
 for p in sorted((source/'src/agentsync').rglob('*.py')):
  relative=p.relative_to(source/'src');name=str(relative).removesuffix('.py').replace('/','.').removesuffix('.__init__')
  module=importlib.import_module(name);origin=pathlib.Path(module.__file__).resolve()
  assert origin==p.resolve()
  observed[str(relative)]=hashlib.sha256(origin.read_bytes()).hexdigest()
 return observed
before=verify();(out/'imports-before.json').write_text(json.dumps(before,indent=2))
import pytest
code=pytest.main(sys.argv[3:]);after=verify();assert before==after
(out/'imports-after.json').write_text(json.dumps(after,indent=2));raise SystemExit(code)
'''
wrapper.write_text("if __name__ == '__main__':\n"+'\n'.join('    '+line for line in wrapper_body.splitlines())+'\n')
command=['/root/jobs-env/bin/python',str(wrapper),str(source),str(evidence),'-p','pytest_asyncio.plugin','-vv','tests','--basetemp',str(root/'test-temp'),'-o','cache_dir='+str(root/'pytest-cache'),'--junitxml',str(evidence/'junit.xml')]
r={'commit':config['commit'],'scope':'complete local Linux SOURCE suite including required real Docker tier; existing dependency venv and pinned preloaded image','image':image,'python':sys.version,'sqlite':sqlite3.sqlite_version,'source_files':len(config['manifest']),'status':'RUNNING','formal_release':'BLOCKED','real_clients':'NOT RUN','deadline_seconds':1200}
def save():(evidence/'result.json').write_text(json.dumps(r,indent=2))
save();began=time.monotonic()
with (evidence/'pytest.log').open('wb') as log:
 p=subprocess.Popen(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 r['owned_pytest_pid']=p.pid;save()
 try:p.wait(timeout=1200);r.update(exit_status=p.returncode,status='COMPLETED')
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGINT)
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  r.update(exit_status=p.returncode,status='TIMED OUT / NOT COMPLETED')
r['wall_seconds']=time.monotonic()-began
r['source_unchanged']=all(hashlib.sha256((source/n).read_bytes()).hexdigest()==h for n,h in config['manifest'].items())
if (evidence/'junit.xml').exists():
 cases=ET.parse(evidence/'junit.xml').getroot().findall('.//testcase')
 r['junit']={'tests':len(cases),'passed':sum(not any(c.find(t) is not None for t in ['failure','error','skipped']) for c in cases),'failed':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skipped':sum(c.find('skipped') is not None for c in cases)}
r['passed']=r.get('exit_status')==0 and r['source_unchanged'] and r['status']=='COMPLETED' and r.get('junit',{}).get('tests',0)==2043 and r['junit']['skipped']==4 and r['junit']['failed']==0 and r['junit']['errors']==0;save()
with tarfile.open(root/'evidence.tar','w') as stream:
 for f in evidence.rglob('*'):
  if f.is_file():stream.add(f,arcname=str(f.relative_to(evidence)),recursive=False)
print(json.dumps({k:v for k,v in r.items() if k!='owned_pytest_pid'}),flush=True)
"""
script=out/'run.sh';script.write_text("set -eu\n/root/jobs-env/bin/python - <<'OWNED_FULL_REGRESSION'\nconfig="+repr(config)+'\n'+body+'\nOWNED_FULL_REGRESSION\n',encoding='utf-8',newline='\n')
py='D:/agentsync-debug/venv/Scripts/python.exe';transport=repo/'tools/local_vm_exec.py'
def call(name,args,timeout):
 p=subprocess.run([py,'-B',str(transport),*args],cwd=repo,capture_output=True,timeout=timeout)
 (out/(name+'.log')).write_bytes(p.stdout+p.stderr);print(name,p.returncode,flush=True)
 if p.returncode:raise SystemExit('Transport failed; inspect guest before retry: '+str(out))
print(out,flush=True)
call('upload',['--upload',str(archive),guest+'.tar'],90)
call('run',['--script',str(script),'--timeout','1300','--log',str(out/'guest.log')],1330)
call('download',['--download',guest+'/evidence.tar',str(out/'evidence.tar')],90)
folder=out/'evidence';folder.mkdir()
with tarfile.open(out/'evidence.tar') as stream:
 for m in stream:
  p=Path(m.name);assert m.isfile() and not p.is_absolute() and '..' not in p.parts
  target=folder/p;assert target.resolve().is_relative_to(folder.resolve());target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stream.extractfile(m).read())
result=json.loads((folder/'result.json').read_text());print(json.dumps(result),flush=True)
raise SystemExit(0 if result['passed'] else 1)

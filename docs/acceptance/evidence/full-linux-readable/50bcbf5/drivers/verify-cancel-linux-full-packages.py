from pathlib import Path
import hashlib,json,subprocess,tarfile,tempfile,uuid
repo=Path('F:/syuc/agentsync-execution-intent');package=Path('D:/agentsync-debug/cancel-full-build-g39f1e5j');parent=json.loads((package/'result.json').read_text());out=Path(tempfile.mkdtemp(prefix='cancel-linux-installed-',dir='D:/agentsync-debug'));guest='/root/agentsync-installed-'+uuid.uuid4().hex;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
wheel=next((package/'artifacts').glob('*.whl'));sdist=next((package/'artifacts').glob('*.tar.gz'));assert all(sha(package/'artifacts'/n)==h for n,h in parent['artifacts'].items())
config={'commit':parent['commit'],'guest':guest,'wheel':wheel.name,'sdist':sdist.name,'artifacts':parent['artifacts'],'modules':parent['runtime_modules'],'selectors':['tests']}
(out/'config.json').write_text(json.dumps(config,indent=2));bundle=out/'bundle.tar'
with tarfile.open(bundle,'w') as stream:
 for path in [wheel,sdist,package/'installed_tests.py',out/'config.json']:stream.add(path,arcname=path.name,recursive=False)
config['bundle_sha256']=sha(bundle)
body=r'''
import contextlib,hashlib,json,os,pathlib,signal,subprocess,sys,tarfile,venv,xml.etree.ElementTree as ET
root=pathlib.Path(config['guest']);bundle=pathlib.Path(config['guest']+'.tar');assert not root.exists() and hashlib.sha256(bundle.read_bytes()).hexdigest()==config['bundle_sha256'];root.mkdir();evidence=root/'evidence';evidence.mkdir()
def extract(archive,dest):
 with tarfile.open(archive) as stream:
  for m in stream:
   p=pathlib.PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts;target=dest/m.name;assert target.resolve().is_relative_to(dest.resolve())
   if m.isdir():target.mkdir(parents=True,exist_ok=True);continue
   assert m.isfile();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stream.extractfile(m).read())
extract(bundle,root)
for name,h in config['artifacts'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h
fixturebase=root/'fixture';fixturebase.mkdir();extract(root/config['sdist'],fixturebase);fixture=next(fixturebase.iterdir());binding=root/'binding.json';binding.write_text(json.dumps(config['modules']))
for name in ['home','tmpbase']:(root/name).mkdir()
env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(root/'home'),'TMPDIR':str(root/'tmpbase'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PIP_NO_INDEX':'1','PIP_CONFIG_FILE':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
image='sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'
assert json.loads(subprocess.run(['docker','image','inspect',image],env=env,capture_output=True,timeout=15,check=True).stdout)[0]['Id']==image
env.update(AGENTSYNC_DOCKER_TEST_IMAGE=image,AGENTSYNC_REQUIRE_DOCKER_TESTS='1')
r={'commit':config['commit'],'version':'0.3.0a28','scope':'complete fresh offline local Linux wheel/sdist suites with required actual Docker; not full OS matrix','steps':[],'packages':{},'formal_release':'BLOCKED','real_clients':'NOT RUN','status':'NOT RUN'}
def save():(evidence/'result.json').write_text(json.dumps(r,indent=2))
def run(name,command,timeout=180):
 p=subprocess.Popen(command,cwd=fixture,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 try:output,_=p.communicate(timeout=timeout);code=p.returncode
 except subprocess.TimeoutExpired:
  with contextlib.suppress(ProcessLookupError):os.killpg(p.pid,signal.SIGKILL)
  output,_=p.communicate();code=None
 log=evidence/(name+'.log');log.write_bytes(output);r['steps'].append({'name':name,'command':command,'exit_code':code,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()});save();print(name,code,flush=True)
 if code!=0:raise RuntimeError('Owned step failed or timed out')
 return output
save()
try:
 for kind,artifact in [('wheel',config['wheel']),('sdist',config['sdist'])]:
  for name,key in [('docker','AGENTSYNC_VERIFIER_EVIDENCE_DIR'),('owner','AGENTSYNC_OWNER_EXECUTOR_EVIDENCE_DIR'),('reconciliation','AGENTSYNC_RECONCILIATION_EVIDENCE_DIR'),('candidate','AGENTSYNC_CANDIDATE_EXECUTOR_EVIDENCE_DIR'),('task-completion','AGENTSYNC_TASK_COMPLETION_EVIDENCE_DIR')]:
   folder=evidence/(kind+'-'+name);folder.mkdir();env[key]=str(folder)
  target=root/kind;venv.EnvBuilder(with_pip=False).create(target);assert 'include-system-site-packages = false' in (target/'pyvenv.cfg').read_text().lower();py=str(target/'bin/python');pip=['/root/jobs-env/bin/python','-m','pip','--python',py]
  if kind=='sdist':run(kind+'-backend',pip+['install','--no-index','--find-links','/root/intent-wheelhouse','--no-cache-dir','setuptools==82.0.1','wheel==0.46.3'])
  run(kind+'-install',pip+['install','--no-index','--find-links','/root/intent-wheelhouse','--no-cache-dir','--no-build-isolation',str(root/artifact)+'[dev]'])
  run(kind+'-tests',[py,'-I',str(root/'installed_tests.py'),str(binding),str(evidence/(kind+'-origins.json')),'-p','pytest_asyncio.plugin',*[str(fixture/s) for s in config['selectors']],'-vv','--durations=20','-o','cache_dir='+str(root/(kind+'-cache')),'--basetemp',str(root/(kind+'-tmp')),'--junitxml',str(evidence/(kind+'-junit.xml'))],1200)
  run(kind+'-dependency-check',pip+['check']);scratch=root/(kind+'-demo');scratch.mkdir();demo=json.loads(run(kind+'-cli',[str(target/'bin/agentsync'),'demo','--workflow','--data-dir',str(scratch)],60));assert demo['data']['outcome']=='simulated_completed' and not list(scratch.iterdir())
  metadata=json.loads(run(kind+'-runtime',[py,'-I','-c','import json,sys,sqlite3,importlib.metadata;print(json.dumps({"python":sys.version,"sqlite":sqlite3.sqlite_version,"distributions":[{"name":d.metadata["Name"],"version":d.version} for d in importlib.metadata.distributions()]}))'],30));(evidence/(kind+'-runtime.json')).write_text(json.dumps(metadata,indent=2))
  cases=list(ET.parse(evidence/(kind+'-junit.xml')).getroot().iter('testcase'));failed=sum(c.find('failure')is not None for c in cases);errors=sum(c.find('error')is not None for c in cases);skipped=sum(c.find('skipped')is not None for c in cases);assert not failed and not errors
  origins=json.loads((evidence/(kind+'-origins.json')).read_text());assert len(origins)==63 and all(pathlib.Path(v['path']).resolve().is_relative_to(target.resolve()) and v['sha256']==config['modules'][n] for n,v in origins.items());assert len(cases)==2043 and skipped==4
  direct=json.loads(run(kind+'-direct-url',[py,'-I','-c','import importlib.metadata,json;d=importlib.metadata.distribution("agentsync-local");assert d.version=="0.3.0a28";print(d.read_text("direct_url.json"))'],30));assert direct['archive_info']['hashes']['sha256']==config['artifacts'][artifact];(evidence/(kind+'-direct-url.json')).write_text(json.dumps(direct,indent=2))
  r['packages'][kind]={'passed':len(cases)-skipped,'failed':failed,'errors':errors,'skipped':skipped,'actual_imports':63,'junit_sha256':hashlib.sha256((evidence/(kind+'-junit.xml')).read_bytes()).hexdigest()};save()
 r['status']='FULL_INSTALLED_SUITES_PASS'
except Exception as error:r['status']='FAILED / NOT COMPLETED';r['error_type']=type(error).__name__
save()
with tarfile.open(root/'evidence.tar','w') as stream:
 for p in evidence.rglob('*'):
  if p.is_file():stream.add(p,arcname=p.relative_to(evidence).as_posix(),recursive=False)
print(json.dumps({'status':r['status'],'packages':r['packages']}),flush=True)
'''
script=out/'run.sh';script.write_text("set -eu\n/root/jobs-env/bin/python - <<'OWNED_INSTALLED_COMPONENTS'\nconfig="+repr(config)+'\n'+body+'\nOWNED_INSTALLED_COMPONENTS\n',encoding='utf-8',newline='\n');transport=repo/'tools/local_vm_exec.py';py='D:/agentsync-debug/venv/Scripts/python.exe';report={'commit':parent['commit'],'guest':guest,'bundle_sha256':sha(bundle),'status':'NOT RUN','steps':[],'formal_release':'BLOCKED'}
def save():(out/'result.json').write_text(json.dumps(report,indent=2))
def call(name,args,timeout):
 p=subprocess.run([py,'-B',str(transport),*args],cwd=repo,capture_output=True,timeout=timeout);log=out/(name+'.log');log.write_bytes(p.stdout+p.stderr);report['steps'].append({'name':name,'exit_code':p.returncode,'log_sha256':sha(log)});save();print(name,p.returncode,flush=True);return p.returncode
print(out,flush=True);save()
if call('upload',['--upload',str(bundle),guest+'.tar'],90):raise SystemExit(2)
if call('run',['--script',str(script),'--timeout','2800','--log',str(out/'guest-run.log')],2830):report['status']='TRANSPORT FAILED / inspect guest before retry';save();raise SystemExit(2)
if call('download',['--download',guest+'/evidence.tar',str(out/'evidence.tar')],90):raise SystemExit(2)
folder=out/'evidence';folder.mkdir()
with tarfile.open(out/'evidence.tar') as stream:
 for m in stream:
  p=Path(m.name);assert m.isfile() and not p.is_absolute() and '..'not in p.parts;target=folder/p;assert target.resolve().is_relative_to(folder.resolve());target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stream.extractfile(m).read())
actual=json.loads((folder/'result.json').read_text());report['guest_result']=actual;report['status']=actual['status'];save();print(actual['status'],actual['packages'],flush=True)

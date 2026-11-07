import hashlib,json,os,subprocess,tarfile,tempfile,xml.etree.ElementTree as ET
from pathlib import Path
repo=Path(r'F:\syuc\agentsync-execution-intent');out=Path(tempfile.mkdtemp(prefix='cancel-full-build-',dir=r'D:\agentsync-debug'))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip()
archive=out/'source.tar';subprocess.run(['git','archive','--format=tar','--output',str(archive),commit],cwd=repo,check=True)
source=out/'source';source.mkdir();manifest={}
with tarfile.open(archive) as stream:
 for m in stream:
  p=Path(m.name);assert not p.is_absolute() and '..' not in p.parts;target=source/p;assert target.resolve().is_relative_to(source.resolve())
  if m.isdir():target.mkdir(parents=True,exist_ok=True);continue
  assert m.isfile();target.parent.mkdir(parents=True,exist_ok=True);data=stream.extractfile(m).read();target.write_bytes(data);manifest[m.name]=hashlib.sha256(data).hexdigest()
modules={n.removeprefix('src/'):h for n,h in manifest.items() if n.startswith('src/agentsync/') and n.endswith('.py')};assert len(modules)>=63
binding=out/'binding.json';binding.write_text(json.dumps(modules))
wrapper=out/'installed_tests.py';wrapper.write_text('''if __name__ == '__main__':
 import hashlib,importlib,json,pathlib,sys
 sys.dont_write_bytecode=True
 expected=json.loads(pathlib.Path(sys.argv[1]).read_text());destination=pathlib.Path(sys.argv[2]);base=pathlib.Path(sys.prefix).resolve()
 def verify():
  result={}
  for relative,digest in expected.items():
   name=relative.removesuffix('.py').replace('/','.').removesuffix('.__init__');module=importlib.import_module(name);origin=pathlib.Path(module.__file__).resolve()
   assert origin.is_relative_to(base) and hashlib.sha256(origin.read_bytes()).hexdigest()==digest
   result[relative]={'path':str(origin),'sha256':digest}
  return result
 before=verify();import agentsync;assert agentsync.__version__=='0.3.0a28'
 import pytest
 code=pytest.main(sys.argv[3:]);after=verify();assert before==after
 destination.write_text(json.dumps(after,indent=2));raise SystemExit(code)
''')
selectors=['tests/integration/test_candidate_execution.py::test_actual_candidate_bytes_not_base_and_old_receipts_stay_immutable','tests/integration/test_candidate_execution.py::test_cleanup_keeps_observation_when_expired_executor_returns','tests/integration/test_candidate_execution.py::test_commit_ack_loss_preserves_fence_before_next_external_step','tests/integration/test_candidate_execution.py::test_schema12_upgrade_preserves_receipt_rows_and_missing_schema_fails_closed','tests/integration/test_candidate_execution.py::test_unavailable_isolation_is_unsupported_without_host_execution']
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT'}}
home=out/'home';home.mkdir();env.update(TEMP=str(out),TMP=str(out),HOME=str(home),USERPROFILE=str(home),PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_CONFIG_FILE=os.devnull,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
py=r'D:\agentsync-debug\venv\Scripts\python.exe';cache=r'D:\agentsync-debug\evidence\windows-final-aac28a0\windows-wheelhouse'
r={'commit':commit,'version':'0.3.0a28','runtime':'WindowsPython3.14','runtime_modules':modules,'source_manifest':manifest,'selectors':selectors,'checks':{},'packages':{},'formal_release':'BLOCKED','real_clients':'NOT RUN'}
def save():(out/'result.json').write_text(json.dumps(r,indent=2))
def run(name,cmd,cwd=out,timeout=300):
 p=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=timeout);(out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr);r['checks'][name]={'exit_status':p.returncode};save();assert p.returncode==0,name;return p
print(out,flush=True);save()
run('build',[py,'-m','build','--wheel','--sdist','--no-isolation','--outdir',str(out/'artifacts'),str(source)])
r['artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'artifacts').iterdir()};save()
r['scope']='build only; no installed test execution';r['source_unchanged']=all(hashlib.sha256((source/n).read_bytes()).hexdigest()==h for n,h in manifest.items());assert r['source_unchanged'];r['passed']=True;save();print(json.dumps({'build_root':str(out),'commit':commit,'artifacts':r['artifacts']}),flush=True)

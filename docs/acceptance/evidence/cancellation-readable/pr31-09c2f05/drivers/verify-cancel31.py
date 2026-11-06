"""Local frozen source and offline installed-package acceptance; no real clients."""
from pathlib import Path
import hashlib, json, os, subprocess, tarfile, tempfile, xml.etree.ElementTree as ET

repo = Path('F:/syuc/agentsync-execution-intent')
out = Path(tempfile.mkdtemp(prefix='cancel31-', dir='D:/agentsync-debug'))
py = 'D:/agentsync-debug/venv/Scripts/python.exe'
py311 = 'D:/agentsync-debug/alpha13-python311-1_06_4p9/venv/Scripts/python.exe'
cache = 'D:/agentsync-debug/evidence/windows-final-aac28a0/windows-wheelhouse'
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip()
archive = out / 'source.tar'
subprocess.run(['git', 'archive', '--format=tar', '--output', str(archive), commit], cwd=repo, check=True)
source = out / 'source'
source.mkdir()
manifest = {}
with tarfile.open(archive) as stream:
    for member in stream:
        target = source / member.name
        assert target.resolve().is_relative_to(source.resolve())
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        assert member.isfile()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = stream.extractfile(member).read()
        target.write_bytes(data)
        manifest[member.name] = hashlib.sha256(data).hexdigest()
modules = {n.removeprefix('src/'): h for n, h in manifest.items() if n.startswith('src/agentsync/') and n.endswith('.py')}
assert len(modules) == 63
binding = out / 'binding.json'
binding.write_text(json.dumps(modules), encoding='utf-8')
wrapper = out / 'test_frozen.py'
wrapper.write_text('''if __name__ == '__main__':
 import hashlib, importlib, json, pathlib, sys
 expected = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
 destination = pathlib.Path(sys.argv[2]); mode = sys.argv[3]
 if mode == 'source': sys.path.insert(0, str(pathlib.Path.cwd() / 'src'))
 base = (pathlib.Path.cwd() / 'src').resolve() if mode == 'source' else pathlib.Path(sys.prefix).resolve()
 def audit():
  result = {}
  for relative, digest in expected.items():
   name = relative.removesuffix('.py').replace('/', '.').removesuffix('.__init__')
   module = importlib.import_module(name); origin = pathlib.Path(module.__file__).resolve()
   assert origin.is_relative_to(base) and hashlib.sha256(origin.read_bytes()).hexdigest() == digest, (name, str(origin))
   result[relative] = {'path': str(origin), 'sha256': digest}
  return result
 before = audit()
 import agentsync, pytest
 assert agentsync.__version__ == '0.3.0a26'
 code = pytest.main(sys.argv[4:])
 after = audit(); assert before == after
 destination.write_text(json.dumps(after, indent=2), encoding='utf-8')
 raise SystemExit(code)
''', encoding='utf-8')
selectors = [
 'tests/unit/test_adapter_run_manager.py',
 'tests/unit/test_mock_run_manager.py',
 'tests/unit/test_cursor_adapter.py',
 'tests/integration/test_adapter_manager_core_boundary.py',
 'tests/integration/test_mock_workflow.py',
 'tests/integration/test_mock_run_manager_core_boundary.py',
 'tests/integration/test_cursor_adapter_core_boundary.py',
]
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'COMSPEC', 'PATHEXT'}}
home = out / 'home'; home.mkdir()
env.update(TEMP=str(out), TMP=str(out), HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_CONFIG_FILE=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, RUFF_CACHE_DIR=str(out/'ruff-cache'), MYPY_CACHE_DIR=str(out/'mypy-cache'))
result = {'commit': commit, 'version': '0.3.0a26', 'source_manifest': manifest, 'runtime_modules': modules, 'selectors': selectors, 'checks': {}, 'suites': {}, 'scope': 'Selected affected Windows source and fresh offline Windows installed-package suites; full repository/Linux/macOS/real clients NOT RUN', 'release': 'BLOCKED'}
def save():
    (out/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
def run(name, args, cwd=source, timeout=240):
    print(name, flush=True)
    try:
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        log = p.stdout + p.stderr
        code = p.returncode
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or b'') + (exc.stderr or b'')
        code = None
    (out/(name+'.log')).write_bytes(log)
    result['checks'][name] = {'exit_code': code, 'log_sha256': hashlib.sha256(log).hexdigest()}
    save()
    assert code == 0, name
def tests(name, python, mode):
    xml = out/(name+'.xml')
    run(name, [str(python), '-I', '-B', str(wrapper), str(binding), str(out/(name+'-origins.json')), mode, '-p', 'pytest_asyncio.plugin', '-q', *selectors, '--junitxml', str(xml), '--basetemp', str(out/(name+'-tmp')), '-o', 'cache_dir='+str(out/(name+'-cache'))])
    cases = list(ET.parse(xml).getroot().iter('testcase'))
    ids = [c.get('classname')+'::'+c.get('name') for c in cases]
    assert len(ids) == len(set(ids))
    result['suites'][name] = {'tests': len(cases), 'passed': sum(not any(c.find(t) is not None for t in ['failure', 'error', 'skipped']) for c in cases), 'failed': sum(c.find('failure') is not None for c in cases), 'errors': sum(c.find('error') is not None for c in cases), 'skipped': sum(c.find('skipped') is not None for c in cases), 'case_ids': ids, 'junit_sha256': hashlib.sha256(xml.read_bytes()).hexdigest()}
    assert len(cases) > 0 and result['suites'][name]['passed'] == len(cases)
    save()
print(out, flush=True); save()
tests('source314', py, 'source')
tests('source311', py311, 'source')
for name, args in [('ruff', ['ruff', 'check', 'src', 'tests', 'tools']), ('format', ['ruff', 'format', '--check', 'src', 'tests', 'tools']), ('mypy', ['mypy', 'src/agentsync'])]:
    run(name, [py, '-m', *args])
run('build', [py, '-m', 'build', '--wheel', '--sdist', '--no-isolation', '--outdir', str(out/'artifacts'), str(source)])
result['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'artifacts').iterdir()}
for kind, artifact in [('wheel', next((out/'artifacts').glob('*.whl'))), ('sdist', next((out/'artifacts').glob('*.tar.gz')))]:
    venv = out/(kind+'-venv'); run(kind+'-venv', [py, '-m', 'venv', str(venv)])
    python = venv/'Scripts/python.exe'
    run(kind+'-tools', [str(python), '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--find-links', cache, 'setuptools==82.0.1', 'wheel==0.46.3', 'pytest==9.1.1', 'pytest-asyncio==1.4.0', 'httpx==0.28.1'])
    run(kind+'-install', [str(python), '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--no-build-isolation', '--find-links', cache, str(artifact)])
    run(kind+'-pipcheck', [str(python), '-m', 'pip', 'check'])
    tests(kind, python, 'installed')
    direct = next((venv/'Lib/site-packages').glob('agentsync_local-*.dist-info/direct_url.json'))
    direct_data = json.loads(direct.read_text(encoding='utf-8'))
    assert direct_data['archive_info']['hashes']['sha256'] == result['artifacts'][artifact.name]
    (out/(kind+'-direct-url.json')).write_text(json.dumps(direct_data, indent=2), encoding='utf-8')
first = set(result['suites']['source314']['case_ids'])
assert all(set(s['case_ids']) == first for s in result['suites'].values())
result['source_unchanged'] = all(hashlib.sha256((source/n).read_bytes()).hexdigest() == h for n, h in manifest.items())
assert result['source_unchanged']
result['passed'] = True; save()
print(json.dumps({'evidence': str(out), 'commit': commit, 'suites': {n: {k: v for k,v in s.items() if k != 'case_ids'} for n,s in result['suites'].items()}, 'artifacts': result['artifacts'], 'passed': True}), flush=True)

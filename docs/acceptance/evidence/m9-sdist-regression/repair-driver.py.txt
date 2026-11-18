"""Guarded full local regression with frozen source and installed-runtime identity."""
from collections import Counter
from datetime import UTC,datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent
SOURCE=BASE/'source'
PACKAGE=BASE
REPAIRED=('tests/unit/test_acceptance_traceability.py','tests/unit/test_release_acceptance.py')

class CollectionReceipt:
    def pytest_collection_finish(self,session):
        cases=[]
        for item in session.items:
            module=item.path.relative_to(SOURCE).as_posix().removesuffix('.py').replace('/','.')
            if item.cls is not None:
                module+='.'+item.cls.__name__
            cases.append({'nodeid':item.nodeid,'classname':module,'name':item.name})
        assert len({(c['classname'],c['name']) for c in cases})==len(cases)
        with (BASE/'collection.json').open('x',encoding='utf-8') as out:
            json.dump({'scope':'Collection only; no tests executed','cases':cases},out,indent=2)

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def fingerprint():
    return {p.relative_to(SOURCE).as_posix():sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}

def identity():
    import agentsync
    config=json.loads((BASE/'identity.json').read_text())
    site=Path(agentsync.__file__).resolve().parent.parent
    assert site.is_relative_to(PACKAGE/('installed' if sys.platform=='win32' else 'venv'))
    for name,expected in config['runtime_members'].items():assert sha(site/name)==expected,name
    for name,module in tuple(sys.modules.items()):
        if name=='agentsync' or name.startswith('agentsync.'):
            assert Path(module.__file__).resolve().is_relative_to(site/'agentsync'),name
    return {'origin':str(site/'agentsync'),'runtime_package_members_matched':len(config['runtime_members']),'runtime_python_modules':sum(name.endswith('.py') for name in config['runtime_members']),'source_shadowing':False}

def main():
    if sys.argv[1:]==['collect']:
        import pytest
        before=identity()
        code=pytest.main([str(SOURCE/'tests'),'--collect-only','-q','-p','no:cacheprovider'],plugins=[CollectionReceipt()])
        assert identity()==before
        return code
    if sys.argv[1:]==['child']:
        import pytest
        before=identity()
        code=pytest.main([*(str(SOURCE/path) for path in REPAIRED),'-q','-p','no:cacheprovider','--basetemp='+str(BASE/'test-tmp'),'--junitxml='+str(BASE/'junit.raw.xml')])
        assert identity()==before
        (BASE/'origin.json').write_text(json.dumps(before|{'verified_before_after':True,'exit_code':code},indent=2))
        return code
    assert not sys.argv[1:] and not (BASE/'result.json').exists()
    config=json.loads((BASE/'identity.json').read_text())
    assert sha(BASE/'agentsync_local-0.3.0a109.tar.gz')==config['sdist_sha256']
    before=fingerprint();identity()
    for name, expected in config['sdist_source_members'].items():
        assert before[name] == expected, name
    for name in ('logs','tmp','home','codex-home'):(BASE/name).mkdir(exist_ok=True)
    for name in tuple(os.environ):
        upper=name.upper()
        if upper.startswith(('PYTEST_','AGENTSYNC_','GIT_','OPENAI_','ANTHROPIC_','CLAUDE_','CURSOR_','AZURE_OPENAI_')) or upper in {'PYTHONPATH','PYTHONHOME','CODEX_HOME','CODEX_API_KEY','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'}:os.environ.pop(name,None)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1',PIP_NO_INDEX='1',PIP_CONFIG_FILE=os.devnull,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,HOME=str(BASE/'home'),USERPROFILE=str(BASE/'home'),CODEX_HOME=str(BASE/'codex-home'),TEMP=str(BASE/'tmp'),TMP=str(BASE/'tmp'),TMPDIR=str(BASE/'tmp'))
    if sys.platform!='win32':os.environ.update(AGENTSYNC_DOCKER_TEST_IMAGE='sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258',AGENTSYNC_REQUIRE_DOCKER_TESTS='1')
    spec=importlib.util.spec_from_file_location('acceptance_collector',SOURCE/'tools/release_acceptance.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    report={key:config[key] for key in ('product_sha','test_source_sha','sdist_sha256','scope')}
    report.update(started_at=datetime.now(UTC).isoformat(),python=sys.version,platform=sys.platform,status='running',model_calls=0,github_actions_used=False,formal_release='BLOCKED')
    (BASE/'result.json').write_text(json.dumps(report,indent=2))
    report['collection_check']=collector.execute('sdist_collect',[sys.executable,'-I','-B',str(Path(__file__).resolve()),'collect'],SOURCE,BASE,BASE/'tmp',pytest_timeout=120)
    assert report['collection_check']['exit_code']==0
    report['rerun_test_files']=list(REPAIRED)
    command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'child']
    report['check']=collector.execute('sdist_pytest',command,SOURCE,BASE,BASE/'tmp',pytest_timeout=3600)
    after=fingerprint()
    report['source_unchanged']=before==after
    report['source_files']=len(before)
    report['source_fingerprint_sha256']=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    report['changed_source_paths']=sorted(name for name in before.keys()|after.keys() if before.get(name)!=after.get(name))
    report['installed_identity']=identity()
    if (BASE/'junit.raw.xml').exists():
        report['junit_redactions']=collector.persist_junit(BASE/'junit.raw.xml',BASE/'junit.xml')
        report['junit']=collector.junit_counts(BASE/'junit.xml')
        cases=list(ET.parse(BASE/'junit.xml').getroot().iter('testcase'))
        report['skip_reasons']=dict(Counter(n.get('message','') for case in cases for n in case.findall('skipped')))
        report['failed_cases']=[{'class':case.get('classname'),'name':case.get('name'),'kind':kind,'message':n.get('message','')} for case in cases for kind in ('failure','error') for n in case.findall(kind)]
    report['status']='pass' if report['check']['exit_code']==0 and report['source_unchanged'] and (BASE/'origin.json').exists() else 'fail'
    report['finished_at']=datetime.now(UTC).isoformat()
    (BASE/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'junit':report.get('junit'),'failed_cases':report.get('failed_cases')}))
    return 0 if report['status']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())

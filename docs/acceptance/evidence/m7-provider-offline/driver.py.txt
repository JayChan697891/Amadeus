"""Bounded provider/traceability regression; source and installed runtime are distinct."""
from collections import Counter
from datetime import UTC,datetime
import hashlib,importlib.metadata,importlib.util,json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent
SOURCE=BASE/'source'
PACKAGE=Path('D:/agentsync-debug/m9-sdist-repair-9fb36a1') if sys.platform=='win32' else Path('/root/amadeus-sdist-repair-9fb36a1')
SELECTORS=('tests/unit/test_http_providers.py','tests/integration/test_provider_loopback_transport.py',
           'tests/unit/test_provider_usage_and_budget.py','tests/unit/test_acceptance_traceability.py',
           'tests/unit/test_release_acceptance.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def fingerprint():return {p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
def identity():
    import agentsync
    config=json.loads((BASE/'identity.json').read_text())
    environment=PACKAGE/('installed' if sys.platform=='win32' else 'venv')
    assert Path(sys.prefix).resolve()==environment.resolve()
    site=Path(agentsync.__file__).resolve().parent.parent
    assert site.is_relative_to(environment)
    direct=json.loads(importlib.metadata.distribution('agentsync-local').read_text('direct_url.json'))
    assert direct['archive_info']['hashes']['sha256']==config['installed_sdist_sha256']
    for name,digest in config['runtime_members'].items():assert sha(site/name)==digest,name
    for name,module in tuple(sys.modules.items()):
        if name=='agentsync' or name.startswith('agentsync.'):
            assert Path(module.__file__).resolve().is_relative_to(site/'agentsync'),name
    return {'origin':str(site/'agentsync'),'runtime_members_matched':len(config['runtime_members']),
            'source_shadowing':False,'installed_sdist_sha256':config['installed_sdist_sha256']}
def main():
    if sys.argv[1:]==['child']:
        import pytest
        before=identity()
        code=pytest.main([*(str(SOURCE/n) for n in SELECTORS),'-q','-p','no:cacheprovider',
                         '--basetemp='+str(BASE/'test-tmp'),'--junitxml='+str(BASE/'junit.raw.xml')])
        assert identity()==before
        (BASE/'origin.json').write_text(json.dumps(before|{'verified_before_after':True,'exit_code':code},indent=2))
        return code
    assert not sys.argv[1:] and not (BASE/'result.json').exists()
    config=json.loads((BASE/'identity.json').read_text())
    assert sha(BASE/'source.zip')==config['source_zip_sha256']
    before=fingerprint();assert before==config['source_members']
    identity()
    for name in tuple(os.environ):
        upper=name.upper()
        if upper.startswith(('PYTEST_','AGENTSYNC_','GIT_','OPENAI_','ANTHROPIC_','CLAUDE_','CURSOR_','AZURE_OPENAI_','GEMINI_','GOOGLE_','DEEPSEEK_')) or upper in {'PYTHONPATH','PYTHONHOME','CODEX_HOME','CODEX_API_KEY','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'}:
            os.environ.pop(name,None)
    for name in ('home','tmp','logs'):(BASE/name).mkdir()
    os.environ.update(HOME=str(BASE/'home'),USERPROFILE=str(BASE/'home'),CODEX_HOME=str(BASE/'home'),
                      TEMP=str(BASE/'tmp'),TMP=str(BASE/'tmp'),TMPDIR=str(BASE/'tmp'),
                      PYTHONDONTWRITEBYTECODE='1',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,
                      PIP_NO_INDEX='1',PIP_CONFIG_FILE=os.devnull)
    spec=importlib.util.spec_from_file_location('collector',SOURCE/'tools/release_acceptance.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    report={k:config[k] for k in ('product_sha','test_source_sha','source_zip_sha256','installed_sdist_sha256','scope')}
    report.update(platform=sys.platform,python=sys.version,started_at=datetime.now(UTC).isoformat(),
                  status='running',model_calls=0,github_actions_used=False,formal_release='BLOCKED')
    (BASE/'result.json').write_text(json.dumps(report,indent=2))
    result=collector.execute('provider_pytest',[sys.executable,'-I','-B',str(Path(__file__).resolve()),'child'],SOURCE,BASE,BASE/'tmp')
    report.update(check=result,source_unchanged=before==fingerprint(),installed_identity=identity(),selectors=list(SELECTORS))
    if (BASE/'junit.raw.xml').exists():
        report['junit_redactions']=collector.persist_junit(BASE/'junit.raw.xml',BASE/'junit.xml')
        report['junit']=collector.junit_counts(BASE/'junit.xml')
        entries=list(ET.parse(BASE/'junit.xml').getroot().iter('testcase'))
        report['skip_reasons']=dict(Counter(n.get('message','') for c in entries for n in c.findall('skipped')))
    report['status']='pass' if result['exit_code']==0 and report['source_unchanged'] and (BASE/'origin.json').exists() else 'fail'
    report['finished_at']=datetime.now(UTC).isoformat()
    (BASE/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'junit':report.get('junit')}))
    return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())

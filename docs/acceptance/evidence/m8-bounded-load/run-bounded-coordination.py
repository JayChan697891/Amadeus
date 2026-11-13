"""One declared, bounded contention diagnostic on a previously verified runtime."""
from datetime import UTC,datetime
import hashlib,importlib.util,json,os,sys
from pathlib import Path

if sys.platform=='win32':
    BASE=Path('D:/agentsync-debug/m8-load-2af7ccc')
    FROZEN=Path('D:/agentsync-debug/m7-providers-2af7ccc')
    ENVIRONMENT=Path('D:/agentsync-debug/m9-sdist-repair-9fb36a1/installed')
else:
    BASE=Path('/root/amadeus-load-2af7ccc')
    FROZEN=Path('/root/amadeus-providers-2af7ccc')
    ENVIRONMENT=Path('/root/amadeus-sdist-repair-9fb36a1/venv')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check_runtime(config):
    import agentsync
    assert Path(sys.prefix).resolve()==ENVIRONMENT.resolve()
    site=Path(agentsync.__file__).resolve().parent.parent
    assert site.is_relative_to(ENVIRONMENT)
    for name,digest in config['runtime_members'].items():assert sha(site/name)==digest,name
    return str(site/'agentsync')

def main():
    BASE.mkdir(mode=0o700)
    for name in ('home','tmp','logs','scratch'):(BASE/name).mkdir(mode=0o700)
    config=json.loads((FROZEN/'identity.json').read_text())
    source=FROZEN/'source'
    for name in ('tools/benchmark_coordination.py','tools/release_acceptance.py'):
        assert sha(source/name)==config['source_members'][name]
    origin=check_runtime(config)
    for name in tuple(os.environ):
        upper=name.upper()
        if upper.startswith(('AGENTSYNC_','GIT_','PYTEST_','OPENAI_','ANTHROPIC_','GEMINI_','GOOGLE_','DEEPSEEK_','CLAUDE_','CURSOR_')) or upper in {'CODEX_HOME','CODEX_API_KEY','PYTHONPATH','PYTHONHOME','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'}:
            os.environ.pop(name,None)
    os.environ.update(HOME=str(BASE/'home'),USERPROFILE=str(BASE/'home'),CODEX_HOME=str(BASE/'home'),
                      TEMP=str(BASE/'tmp'),TMP=str(BASE/'tmp'),TMPDIR=str(BASE/'tmp'),
                      GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,PYTHONDONTWRITEBYTECODE='1')
    spec=importlib.util.spec_from_file_location('collector',source/'tools/release_acceptance.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    report={'runtime_sha':config['product_sha'],'tool_source_sha':config['test_source_sha'],
            'platform':sys.platform,'python':sys.version,'started_at':datetime.now(UTC).isoformat(),
            'scope':'Bounded local diagnostic, not exhaustive stress or Release SLO',
            'status':'running','checks':[],'model_calls':0,'github_actions_used':False,
            'formal_release':'BLOCKED','runtime_origin':origin}
    (BASE/'result.json').write_text(json.dumps(report,indent=2))
    for name,workers,extra in (('threads',4,()),('process-http',2,('--processes','--transport-mix'))):
        command=[sys.executable,'-I','-B',str(source/'tools/benchmark_coordination.py'),
                 '--scratch-parent',str(BASE/'scratch'),'--workers',str(workers),
                 '--rounds','20','--p95-budget-ms','1000',*extra]
        check=collector.execute(name,command,BASE,BASE,BASE/'tmp')
        row={'process':check}
        if check['exit_code']==0:
            diagnostic=json.loads((BASE/check['log']).read_text())
            assert diagnostic['workload']['workers']==workers and diagnostic['workload']['rounds']==20
            assert diagnostic['passed'] and diagnostic['diagnostic_only'] and not diagnostic['formal_acceptance']
            assert diagnostic['claim_audit']['expected']==workers*20
            row['diagnostic']=diagnostic
        report['checks'].append(row)
        (BASE/'result.json').write_text(json.dumps(report,indent=2))
    assert check_runtime(config)==origin
    report['runtime_members_matched_before_after']=90
    report['scratch_empty_after']=not any((BASE/'scratch').iterdir())
    report['status']='pass' if all(r['process']['exit_code']==0 for r in report['checks']) and report['scratch_empty_after'] else 'fail'
    report['finished_at']=datetime.now(UTC).isoformat()
    (BASE/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'results':[
        {'mode':r['process']['id'],'exit':r['process']['exit_code'],
         'p95_ms':r.get('diagnostic',{}).get('claim_latency_ms',{}).get('p95'),
         'functional_checks':r.get('diagnostic',{}).get('functional_checks')} for r in report['checks']]}))
    return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())

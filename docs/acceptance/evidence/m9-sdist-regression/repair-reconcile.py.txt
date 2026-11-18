"""Bind retained full-run cases and explicit delta reruns without rewriting failures."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
OLD = BASE.parent / 'm9-sdist-c262a29'
REPO = Path('F:/syuc/amadeus-m6-single')
REPAIRED = {'tests/unit/test_acceptance_traceability.py', 'tests/unit/test_release_acceptance.py'}
spec=importlib.util.spec_from_file_location('collector',BASE/'source/tools/release_acceptance.py')
collector=importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
DOCS = {'README.md', 'README.zh-CN.md', 'docs/COMPATIBILITY.md', 'docs/M6-ADAPTERS.md',
        'docs/PROGRESS.md', 'docs/acceptance/CLIENT-MATRIX.md',
        'docs/acceptance/INSTALLATION-REPORT.md', 'docs/acceptance/PACKAGE-INSTALLATION.md'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cases(path):
    entries = list(ET.parse(path).getroot().iter('testcase'))
    result = {(c.get('classname'), c.get('name')): c for c in entries}
    assert len(entries) == len(result), 'Duplicate case identities'
    return result

def state(case):
    for name in ('failure', 'error', 'skipped'):
        if case.find(name) is not None:
            return name
    return 'passed'

old, new = read(OLD/'identity.json'), read(BASE/'identity.json')
assert old['product_sha'] == new['product_sha']
assert old['runtime_members'] == new['runtime_members']
old_files, new_files = old['sdist_source_members'], new['sdist_source_members']
assert old_files.keys() == new_files.keys()
changed = {name for name in old_files if old_files[name] != new_files[name]}
assert changed - DOCS == REPAIRED, changed
assert changed <= DOCS | REPAIRED
assert sha(OLD/'agentsync_local-0.3.0a109.tar.gz') == old['sdist_sha256']
assert sha(BASE/'agentsync_local-0.3.0a109.tar.gz') == new['sdist_sha256']
diff = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only',
                               old['test_source_sha'], new['test_source_sha']]).decode().splitlines()
assert set(diff) == changed
batch_input = ''.join(new['test_source_sha']+':'+name+'\n' for name in new_files).encode()
batch = subprocess.check_output(['git','-C',str(REPO),'cat-file','--batch'],input=batch_input)
offset = 0
for name,digest in new_files.items():
    header_end=batch.index(b'\n',offset)
    _,kind,size=batch[offset:header_end].split()
    assert kind==b'blob'
    offset=header_end+1
    blob=batch[offset:offset+int(size)]
    assert hashlib.sha256(blob).hexdigest()==digest,name
    offset+=int(size)
    assert batch[offset:offset+1]==b'\n'
    offset+=1
assert offset==len(batch)

platforms, effective, report_files = {}, {}, {}
for platform, prefix in (('windows', ''), ('linux', 'linux-')):
    before_path, after_path = OLD/(prefix+'junit.xml'), BASE/(prefix+'junit.xml')
    before, after = cases(before_path), cases(after_path)
    collection = read(BASE/(prefix+'collection.json'))['cases']
    # JUnit persistence redacts each XML attribute independently. Apply the same
    # existing transform to collected fixture IDs before comparing identities.
    collection_redactions=0
    for case in collection:
        for key in ('classname','name','nodeid'):
            case[key],count=collector.redact_credentials(case[key])
            collection_redactions+=count
    collected = {(c['classname'], c['name']): c for c in collection}
    assert len(collection) == len(collected) == len(before) == 2334
    assert before.keys() == collected.keys()
    selected = {key for key, c in collected.items() if c['nodeid'].split('::')[0] in REPAIRED}
    assert selected == after.keys() and len(after) == 246
    assert all(state(c) == 'passed' for c in after.values())
    failed = {key for key, c in before.items() if state(c) in {'failure', 'error'}}
    assert len(failed) == 4 and failed <= selected
    original_result, delta_result = read(OLD/(prefix+'result.json')), read(BASE/(prefix+'result-repaired.json'))
    assert original_result['status'] == 'fail' and delta_result['status'] == 'pass'
    assert original_result['source_unchanged'] and delta_result['source_unchanged']
    assert delta_result['collection_check']['exit_code'] == 0
    for root, result, log_prefix in ((OLD, original_result, prefix), (BASE, delta_result, prefix)):
        log = root / (log_prefix+Path(result['check']['log']).name) if prefix else root/result['check']['log']
        assert sha(log) == result['check']['log_sha256']
        origin = read(root/(prefix+'origin.json'))
        assert origin['verified_before_after'] and not origin['source_shadowing']
        assert origin['runtime_package_members_matched'] == 90
    install = read(BASE/(prefix+'installation-observation.json'))
    assert install['sdist_sha256'] == new['sdist_sha256'] and install['runtime_members_matched'] == 90
    assert install['sdk_smoke'] == install['console_smoke']['status'] == 'pass'
    effective[platform] = {key: after[key] if key in selected else case for key, case in before.items()}
    assert not any(state(c) in {'failure', 'error'} for c in effective[platform].values())
    platforms[platform] = {
        'original_full_run': dict(Counter(state(c) for c in before.values())),
        'delta_run': dict(Counter(state(c) for c in after.values())),
        'combined_results': dict(Counter(state(c) for c in effective[platform].values())),
        'original_full_run_remains_failed': True,
        'full_suite_rerun_on_new_sha': False,
        'collection_matches_original_all_2334_cases': True,
        'collection_fixture_id_redactions':collection_redactions,
        'unchanged_cases_reused': len(before)-len(after),
        'superseded_failure_ids': [list(key) for key in sorted(failed)],
    }
    report_files[platform] = [
        {'nodeid': collected[key]['nodeid'], 'classname': key[0], 'name': key[1],
         'outcome': state(case), 'evidence': 'repair-junit' if key in selected else 'original-full-junit'}
        for key, case in sorted(effective[platform].items())
    ]

skips=[]
for platform, entries in effective.items():
    other=effective['linux' if platform=='windows' else 'windows']
    for key, case in entries.items():
        if state(case)=='skipped':
            skips.append({'platform':platform,'case':list(key),
                          'reason':case.find('skipped').get('message'),
                          'other_platform_pass':state(other[key])=='passed'})
assert len(skips)==61 and all(s['other_platform_pass'] for s in skips)
record={'schema':'amadeus.full-plus-affected-rerun.v1',
        'scope':'Retained c262 full results plus 9fb36a1 affected-file reruns, not a new full run',
        'original_full_source_sha':old['test_source_sha'],'repair_source_sha':new['test_source_sha'],
        'runtime_sha':new['product_sha'],'original_sdist_sha256':old['sdist_sha256'],
        'repair_sdist_sha256':new['sdist_sha256'],'git_matched_repair_files':len(new_files),
        'runtime_members_unchanged':len(new['runtime_members']),
        'changed_files':sorted(changed),'unchanged_dependency_inputs':True,
        'platforms':platforms,'skips':skips,'model_calls':0,'github_actions_used':False,
        'formal_release':'BLOCKED','independent_review':'pending'}
with (BASE/'reconciliation.json').open('x',encoding='utf-8') as out:
    json.dump(record,out,indent=2);out.write('\n')
with (BASE/'case-provenance.json').open('x',encoding='utf-8') as out:
    json.dump(report_files,out,indent=2);out.write('\n')
print(json.dumps({'platforms':platforms,'git_matched_repair_files':len(new_files),
                  'skip_count':len(skips),'formal_release':'BLOCKED'}))

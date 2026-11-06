import hashlib,io,json,subprocess,tarfile,xml.etree.ElementTree as ET
from pathlib import Path
repo=Path('F:/syuc/agentsync-execution-intent');dest=Path('D:/agentsync-debug/cancel-stack-delivery');dest.mkdir(exist_ok=True)
reviewpath=Path('D:/agentsync-debug/astra-internal-cancel-review.json');review=json.loads(reviewpath.read_text(encoding='utf-8'))
assert review.get('open_blockers',[])==[]
entries=[(31,'cancel31-w6bv2b8w','0.3.0a26',['alpha26-lifecycle-vcrr1usf']),(32,'cancel32-a2zmz9oj','0.3.0a27',['alpha27-workflow-6g0at8nh','alpha26-lifecycle-vcrr1usf']),(33,'cancel33-hc72z3ls','0.3.0a28',['alpha28-codex-version-_s__lqtm'])]
allresults=[]
for pr,folder,version,oldfolders in entries:
 out=Path('D:/agentsync-debug')/folder;r=json.loads((out/'result.json').read_text(encoding='utf-8'));assert r['passed'];sha=r['commit'];sets=[]
 expected=review.get('reviewed_files_sha256',review.get('reviewed_files',{}));assert len(expected)>=2
 for n,h in expected.items():assert r['source_manifest'][n]==h
 for n,h in r['source_manifest'].items():
  assert hashlib.sha256(subprocess.check_output(['git','show',sha+':'+n],cwd=repo)).hexdigest()==h
  assert hashlib.sha256((out/'source'/n).read_bytes()).hexdigest()==h
 for name,s in r['suites'].items():
  xml=out/(name+'.xml');cases=list(ET.parse(xml).getroot().iter('testcase'));ids={c.get('classname')+'::'+c.get('name') for c in cases}
  assert len(ids)==len(cases)==s['passed'] and not any(c.find(t)is not None for c in cases for t in ('failure','error','skipped'))
  assert hashlib.sha256(xml.read_bytes()).hexdigest()==s['junit_sha256'];sets.append(ids)
  origins=json.loads((out/(name+'-origins.json')).read_text(encoding='utf-8'));assert len(origins)==63
  base=(out/'source/src').resolve() if name.startswith('source') else (out/(name+'-venv')).resolve()
  for n,item in origins.items():
   p=Path(item['path']).resolve();assert p.is_relative_to(base) and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']==r['runtime_modules'][n]
 assert len(sets)==4 and all(s==sets[0] for s in sets)
 classes={i.rsplit('::',1)[0] for i in sets[0]};oldids=set()
 for oldfolder in oldfolders:
  cases=ET.parse(Path('D:/agentsync-debug')/oldfolder/'source314.xml').getroot().iter('testcase')
  oldids|={c.get('classname')+'::'+c.get('name') for c in cases if c.get('classname') in classes}
 assert oldids<=sets[0] and len(sets[0]-oldids)==27
 for n,c in r['checks'].items():assert c['exit_code']==0 and hashlib.sha256((out/(n+'.log')).read_bytes()).hexdigest()==c['log_sha256']
 for n,h in r['artifacts'].items():assert hashlib.sha256((out/'artifacts'/n).read_bytes()).hexdigest()==h
 matched=0
 with tarfile.open(next((out/'artifacts').glob('*.tar.gz'))) as stream:
  for m in stream:
   n='/'.join(Path(m.name).parts[1:])
   if m.isfile() and n in r['source_manifest']:
    assert hashlib.sha256(stream.extractfile(m).read()).hexdigest()==r['source_manifest'][n];matched+=1
 audit={'source_commit':sha,'git_files':len(r['source_manifest']),'runtime_modules_each':63,'sdist_matching_git_members':matched,'unique_cases_each':len(sets[0]),'retained_cases':len(oldids),'new_cancellation_cases':27,'checks':'Independent Git/file/origin/JUnit/log/artifact bytes PASS'}
 (out/'root-cancel-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
 members={'review/astra-internal-cancel-review.json':reviewpath,'drivers/finalize-cancellation-stack.py':Path(__file__),'drivers/verify-cancel'+str(pr)+'.py':Path('D:/agentsync-debug/verify-cancel'+str(pr)+'.py')}
 for p in out.iterdir():
  if p.is_file() and p.suffix in {'.json','.log','.xml','.py'}:members['evidence/'+p.name]=p
 for p in (out/'artifacts').iterdir():members['artifacts/'+p.name]=p
 for p in Path('D:/agentsync-debug/m6-internal-cancel-sol').iterdir():
  if p.is_file() and p.suffix in {'.log','.xml'}:members['development/'+p.name]=p
 manifest={n:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for n,p in members.items()}
 archive=dest/('cancel-pr'+str(pr)+'-'+sha[:7]+'.tar.gz');assert not archive.exists()
 with tarfile.open(archive,'w:gz') as stream:
  for n,p in members.items():stream.add(p,arcname=n,recursive=False)
  raw=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('MANIFEST.json');info.size=len(raw);stream.addfile(info,io.BytesIO(raw))
 with tarfile.open(archive) as stream:
  for n,record in manifest.items():
   raw=stream.extractfile(n).read();assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256']
 summary={'schema':'agentsync.local-checkpoint.v1','pr':pr,'version':version,'source_commit':sha,'scope':'Work PR31 cancellation privacy repair and repaired inherited baseline; no full B3/client acceptance','suites':{n:{k:v for k,v in s.items() if k!='case_ids'} for n,s in r['suites'].items()},'identity':audit,'archive':'releases/'+version+'/checkpoints/'+archive.name,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'manifest_members':len(manifest),'static':'Ruff/format/mypy63 PASS','independent_review':'Astra static source/hash review; no tests run by reviewer; Work pending','policy':'Outstanding cancellation prevents adapter entry and is normalized to message-free CancelledError; internally raised CancelledError without pending request maps to static error. Counts are policy, not authenticated origin; uncancel required for swallowed requests. Success path rechecks pending state.','red_evidence':'Initial26 regressions and additional successful-return regression1 retained','not_run':['whole repository/Linux/macOS at this SHA','real clients/model tasks','autonomous relay','formal42 acceptance'],'release':'BLOCKED'}
 (dest/('pr'+str(pr)+'.json')).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');allresults.append(summary)
 print(json.dumps({'pr':pr,'source':sha,'each_passed':len(sets[0]),'archive':archive.name,'sha256':summary['archive_sha256']}),flush=True)
(dest/'stack-summary.json').write_text(json.dumps(allresults,indent=2),encoding='utf-8')

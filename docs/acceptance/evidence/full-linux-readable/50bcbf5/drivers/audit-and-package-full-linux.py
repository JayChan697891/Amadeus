import hashlib,json,subprocess,tarfile,io,re,xml.etree.ElementTree as ET
from pathlib import Path
repo=Path('F:/syuc/agentsync-execution-intent');src=Path('D:/agentsync-debug/cancel-linux-full-h1ma9gdf');inst=Path('D:/agentsync-debug/cancel-linux-installed-z4u0xy6v');build=Path('D:/agentsync-debug/cancel-full-build-g39f1e5j')
config=json.loads((src/'config.json').read_text());sha=config['commit'];b=json.loads((build/'result.json').read_text());assert b['commit']==sha
for n,h in config['manifest'].items():assert hashlib.sha256(subprocess.check_output(['git','show',sha+':'+n],cwd=repo)).hexdigest()==h
modules={n.removeprefix('src/'):h for n,h in config['manifest'].items() if n.startswith('src/agentsync/') and n.endswith('.py')};assert len(modules)==63
before=json.loads((src/'evidence/imports-before.json').read_text());after=json.loads((src/'evidence/imports-after.json').read_text());assert before==after==modules
groups={'source':src/'evidence/junit.xml','wheel':inst/'evidence/wheel-junit.xml','sdist':inst/'evidence/sdist-junit.xml'};sets={};skips={}
for name,p in groups.items():
 cases=list(ET.parse(p).getroot().iter('testcase'));ids={c.get('classname')+'::'+c.get('name') for c in cases};assert len(ids)==len(cases)==2043
 assert not any(c.find(t)is not None for c in cases for t in ('failure','error'))
 skips[name]=[{'id':c.get('classname')+'::'+c.get('name'),'reason':c.find('skipped').get('message')} for c in cases if c.find('skipped')is not None];assert len(skips[name])==4;sets[name]=ids
assert all(s==sets['source'] for s in sets.values())
old={c.get('classname')+'::'+c.get('name') for c in ET.parse('D:/agentsync-debug/alpha23-linux-full-9s8fju3r/evidence/junit.xml').getroot().iter('testcase')};assert len(old)==1899 and old<=sets['source']
for kind in ('wheel','sdist'):
 origins=json.loads((inst/'evidence'/(kind+'-origins.json')).read_text());assert set(origins)==set(modules)
 for n,o in origins.items():assert o['sha256']==modules[n] and '/'+kind+'/lib/' in o['path'] and '/site-packages/' in o['path']
 direct=json.loads((inst/'evidence'/(kind+'-direct-url.json')).read_text());name=next(n for n in b['artifacts'] if n.endswith('.whl' if kind=='wheel' else '.tar.gz'));assert direct['archive_info']['hashes']['sha256']==b['artifacts'][name]
for name,h in b['artifacts'].items():assert hashlib.sha256((build/'artifacts'/name).read_bytes()).hexdigest()==h
ids=set();records=0
def scan(value,key=''):
 if isinstance(value,dict):
  for k,v in value.items():scan(v,k)
 elif isinstance(value,list):
  for v in value:scan(v,key)
 elif isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) and any(t in key.lower() for t in ('container','backend_ref')):ids.add(value)
for root in (src/'evidence',inst/'evidence'):
 for p in root.rglob('*.json'):
  if p.name in {'result.json','image.json'} or 'origins' in p.name or 'runtime' in p.name or 'imports-' in p.name:continue
  value=json.loads(p.read_text());scan(value)
  if 'docker' in p.as_posix() or any(t in p.as_posix() for t in ('candidate','completion','owner','reconciliation')):records+=1
result={'source_commit':sha,'git_inputs':len(config['manifest']),'runtime_modules_each':63,'source_wheel_sdist_each':{'tests':2043,'passed':2039,'skipped':4,'failed':0,'errors':0},'retained':1899,'added':144,'skips':skips,'artifacts':b['artifacts'],'recorded_container_ids':sorted(ids),'json_observations':records,'container_postcheck':'PENDING','vm_old11692_shutdown':'Not observed running on resume; no graceful shutdown claim','release':'BLOCKED'}
(src/'root-full-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('skips','recorded_container_ids')},indent=2));print('Recorded IDs',len(ids))

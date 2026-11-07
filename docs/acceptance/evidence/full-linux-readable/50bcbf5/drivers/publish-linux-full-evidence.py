import hashlib,io,json,subprocess,tarfile
from pathlib import Path
repo=Path('F:/syuc/agentsync-execution-intent');src=Path('D:/agentsync-debug/cancel-linux-full-h1ma9gdf');inst=Path('D:/agentsync-debug/cancel-linux-installed-z4u0xy6v');build=Path('D:/agentsync-debug/cancel-full-build-g39f1e5j')
audit=json.loads((src/'root-full-audit.json').read_text());reviewpath=Path('D:/agentsync-debug/astra-linux-full-final.json');review=json.loads(reviewpath.read_text());assert review['findings']==[] and review['reviewed_sha']==audit['source_commit']
post=Path('D:/agentsync-debug/full-container-postcheck.json');closed=Path('D:/agentsync-debug/vm/startup-poweroff-result.json');p=json.loads(post.read_text());c=json.loads(closed.read_text(encoding='utf-8-sig'))
assert p['all_recorded_ids_absent'] and p['recorded_ids']==96 and c['stopped'] and c['verified_owned_pid']==5552 and not c['forced_stop_used']
assert not subprocess.check_output(['git','diff','--name-only',audit['source_commit'],'HEAD','--','src','tests','tools','pyproject.toml'],cwd=repo,text=True).strip()
members={}
for prefix,folder in [('source',src/'evidence'),('installed',inst/'evidence')]:
 for path in folder.rglob('*'):
  if path.is_file():members[prefix+'/'+path.relative_to(folder).as_posix()]=path
for path in (build/'artifacts').iterdir():members['artifacts/'+path.name]=path
for label,path in [('source-config.json',src/'config.json'),('build-result.json',build/'result.json'),('root-audit.json',src/'root-full-audit.json'),('astra-review.json',reviewpath),('container-postcheck.json',post),('owned-vm-shutdown.json',closed)]:members[label]=path
for name in ['run-cancel-linux-full.py','build-cancel-full-packages.py','verify-cancel-linux-full-packages.py','audit-and-package-full-linux.py','postcheck-full-containers.sh','publish-linux-full-evidence.py']:
 members['drivers/'+name]=Path('D:/agentsync-debug')/name
manifest={n:{'bytes':v.stat().st_size,'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for n,v in members.items()}
archive=repo/'releases/0.3.0a28/checkpoints/full-linux-50bcbf5.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz') as stream:
 for n,v in members.items():stream.add(v,arcname=n,recursive=False)
 raw=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('MANIFEST.json');info.size=len(raw);stream.addfile(info,io.BytesIO(raw))
with tarfile.open(archive) as stream:
 for n,item in manifest.items():
  raw=stream.extractfile(n).read();assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
root=repo/'docs/acceptance/evidence/full-linux-readable/50bcbf5';assert not root.exists();root.mkdir(parents=True)
readable={}
for n,v in members.items():
 if v.suffix not in {'.xml','.json','.log','.py','.sh'}:continue
 raw=v.read_bytes();raw.decode('utf-8-sig');target=root/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 readable[n]={**manifest[n],'git_blob_sha1':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()}
(root/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
summary={'schema':'agentsync.full-linux-checkpoint.v1','source_commit':audit['source_commit'],'source_wheel_sdist_each':audit['source_wheel_sdist_each'],'identity':{k:v for k,v in audit.items() if k not in ('skips','recorded_container_ids')},'skips':audit['skips'],'sdist_members':'365 total:357 Git-matched and8generated; independently checked','recorded_container_ids_absent':96,'owned_vm5552_gracefully_stopped':True,'earlier_vm11692_shutdown':'Unobserved; no graceful shutdown claim','independent_audit':'Astra38data checks pass, no findings; reviewer did not run tests','archive':archive.relative_to(repo).as_posix(),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'manifest_members':len(manifest),'readable_path':root.relative_to(repo).as_posix(),'readable_members':readable,'Work':'New Linux evidence PENDING; earlier PR33 limited component accepted at08a3e93','not_run':['full Windows/macOS at this SHA','real model/client tasks','autonomous relay','formal42 acceptance'],'release':'BLOCKED','bootstrap_notes':['Initial shell poststart check used stale LASTEXITCODE; actual VM identity verified without relaunch','Initial SSH connection before guest readiness failed; serial readiness observed and read-only preflight succeeded; no product tests executed during failed transport']}
(root/'INDEX.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8',newline='\n')
(repo/'docs/acceptance/evidence/full-linux-50bcbf5-summary.json').write_text(json.dumps({k:v for k,v in summary.items() if k!='readable_members'},indent=2)+'\n',encoding='utf-8',newline='\n')
attributes=repo/'.gitattributes';s=attributes.read_text(encoding='utf-8');s+='\ndocs/acceptance/evidence/full-linux-readable/** -text\n';attributes.write_text(s,encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('readable_members','skips','identity')},indent=2))

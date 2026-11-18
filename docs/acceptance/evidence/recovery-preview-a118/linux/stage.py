import hashlib
import json
import shlex
from datetime import UTC, datetime
from pathlib import Path
import paramiko

base=Path(__file__).resolve().parent
previous=Path('D:/agentsync-debug/m118p')
files={
 'run-preview.py':Path('D:/agentsync-debug/m118l/run-preview.py'),
 'source.zip':previous/'source.zip',
 'source-manifest.json':previous/'run/source-manifest.json',
 'runtime-members.json':previous/'run/runtime-members.json',
 'agentsync_local-0.3.0a118-py3-none-any.whl':previous/'dist/agentsync_local-0.3.0a118-py3-none-any.whl',
 'agentsync_local-0.3.0a118.tar.gz':previous/'dist/agentsync_local-0.3.0a118.tar.gz',
}
assert hashlib.sha256(files['run-preview.py'].read_bytes()).hexdigest()=='dc39e973274bf9f7ddc0e44e4cfb1081b896841a3e409db4a0eb184f8afa4c37'
vm=Path('D:/agentsync-debug/vm');guest='/root/amadeus-m118l'
client=paramiko.SSHClient();client.load_host_keys(str(vm/'known_hosts'));client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('127.0.0.1',port=22222,username='root',key_filename=str(vm/'debug_ed25519'),look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
probe='''
import json,os,sys
from pathlib import Path
assert sys.version_info[:3]==(3,14,7)
workers=[]
for p in Path('/proc').iterdir():
 if not p.name.isdecimal() or int(p.name)==os.getpid(): continue
 try:
  name=(p/'exe').resolve(strict=True).name
  if name.startswith(('python','codex')):workers.append({'pid':int(p.name),'name':name})
 except (FileNotFoundError,PermissionError): pass
assert not workers
space=os.statvfs('/root');free=space.f_bavail*space.f_frsize
assert free>1024**3
assert Path('/root/intent-wheelhouse').is_dir()
print(json.dumps({'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'workers':workers,'free_bytes':free,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''
try:
 _,out,err=client.exec_command(shlex.join(['/root/jobs-env/bin/python','-I','-B','-c',probe]),timeout=30)
 stdout,stderr=out.read(65537),err.read(65537);code=out.channel.recv_exit_status()
 assert code==0 and not stderr
 record={'observed_at':datetime.now(UTC).isoformat(),'preflight':json.loads(stdout),'files':[],'model_calls':0,'auth_copies':0,'candidate_packages_rebuilt':False}
 with client.open_sftp() as sftp:
  sftp.mkdir(guest,mode=0o700)
  for name,path in files.items():
   data=path.read_bytes();pin=hashlib.sha256(data).hexdigest()
   with sftp.open(guest+'/'+name,'wx') as f:f.write(data)
   sftp.chmod(guest+'/'+name,0o600)
   with sftp.open(guest+'/'+name,'rb') as f:actual=f.read()
   assert actual==data
   record['files'].append({'path':name,'bytes':len(data),'sha256':pin})
 with (base/'staged.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
 print(json.dumps({'guest':guest,'files':len(files),'preflight':record['preflight']}))
finally:client.close()

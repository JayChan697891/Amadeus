set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import json, os, subprocess
from pathlib import Path
workers=[]
for p in Path('/proc').iterdir():
    if not p.name.isdecimal() or int(p.name)==os.getpid(): continue
    try:
        name=(p/'exe').resolve(strict=True).name
        if name.startswith(('python','codex')): workers.append({'pid':int(p.name),'name':name})
    except (FileNotFoundError, PermissionError): pass
containers=subprocess.run(['docker','ps','-aq'],capture_output=True,check=True,text=True).stdout.splitlines()
assert not workers and not containers
print(json.dumps({'workers':workers,'containers':containers,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}),flush=True)
PY
/sbin/poweroff

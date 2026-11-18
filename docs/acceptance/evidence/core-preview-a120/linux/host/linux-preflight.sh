set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import json, os, pathlib, shutil, sys
base=pathlib.Path('/root/amadeus-m120l')
assert not base.exists() and not base.is_symlink(), 'New test root required'
assert sys.version_info[:3] == (3,14,7)
active=[]
for p in pathlib.Path('/proc').iterdir():
    if not p.name.isdecimal() or int(p.name)==os.getpid(): continue
    try:
        comm=(p/'comm').read_text().strip()
        command=(p/'cmdline').read_bytes()
        if ('python' in comm or 'codex' in comm) and any(tag in command for tag in (b'/root/amadeus-',b'/root/agentsync-')): active.append({'pid':int(p.name),'name':comm})
    except (OSError,ProcessLookupError): pass
assert not active, 'Existing project worker must be preserved'
free=shutil.disk_usage('/root').free
assert free > 1024**3
base.mkdir(mode=0o700)
print(json.dumps({'python':sys.version,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'active_project_workers':active,'free_bytes':free,'new_root':str(base),'model_calls':0,'candidate_executions':0}))
PY
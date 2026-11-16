import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
REPO=Path('F:/syuc/amadeus-m6-single')
PYTHON=Path('D:/agentsync-debug/m118p/w/Scripts/python.exe')
BINARY=Path('C:/Users/JayChan/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe')
PROBE=REPO/'tests/manual/probe_codex_collaboration.py'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
expected='72a0c6c8b4532ebb1d9a02ed97aab146fc0ce93f15f249237560b1e4c767ac64'
assert sha(PROBE)==expected
members=json.loads(Path('D:/agentsync-debug/m118p/run/runtime-members.json').read_bytes())
site=PYTHON.parent.parent/'Lib/site-packages'
def installed():
    assert len(members)==97 and all(sha(site/name)==pin for name,pin in members.items())
installed()
command=[str(PYTHON),'-I','-B',str(PROBE),'--codex-binary',str(BINARY),'--scratch-parent',str(BASE)]
record={'started_at':datetime.now(UTC).isoformat(),'command':command,'probe_sha256':expected,'runtime_members_before':97,'models_requested':0,'auth_copies':0}
with (BASE/'start.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
with (BASE/'stdout.log').open('xb') as out,(BASE/'stderr.log').open('xb') as err:
    child=subprocess.run(command,cwd=BASE,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
installed()
assert sha(PROBE)==expected
record.update(finished_at=datetime.now(UTC).isoformat(),exit_code=child.returncode,runtime_members_after=97,probe_unchanged=True)
with (BASE/'terminal.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
raise SystemExit(child.returncode)

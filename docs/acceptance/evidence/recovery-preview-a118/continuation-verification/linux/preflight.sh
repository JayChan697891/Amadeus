set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import json,subprocess
from pathlib import Path
commands=[['/root/amadeus-m118l/w/bin/python','-V'],['docker','info','--format','{{json .SecurityOptions}}'],['docker','image','inspect','sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258','--format','{{json .Id}}'],['docker','ps','--format','{{.ID}} {{.Names}}']]
for command in commands:
 r=subprocess.run(command,capture_output=True,text=True,timeout=20)
 print(json.dumps({'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
 if r.returncode:raise SystemExit(r.returncode)
print(json.dumps({'new_fixture_absent':not Path('/root/amadeus-continuation-bridge-20261116').exists()}))
PY

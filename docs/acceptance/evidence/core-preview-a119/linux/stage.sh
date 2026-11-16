set -eu
/root/jobs-env/bin/python -I -B - <<'PY'
import hashlib,zipfile
from pathlib import Path
p=Path('/root/amadeus-m119l-inputs.zip')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='4c93735cdb69b59fcfb752191e6036184fc4078900c23353950d3790e1cda8ae'
expected={'source.zip': 'b2692874a931de9ca0dffa0abd2bfe3bff2713d972b3f8495ceddce1df55f628', 'source-manifest.json': 'a2985b3cabd623bb1a867d39ddc17de13c81cf8e131db4f91545f32defad25d9', 'runtime-members.json': '545b490670bdbb0f73a74fb13dca77cf9b875c38f350d5a1b2f0f4fdb3b829a7', 'agentsync_local-0.3.0a119-py3-none-any.whl': 'cbcf38bfe80a61510cbc95fb2a7112173222a7b6bb03404a324e52e23d237c31', 'agentsync_local-0.3.0a119.tar.gz': '249f726f5c484c101337546aa137151418829eca1bb0b1a5f21f89c97e1e014e', 'linux-run-preview.py': '0607bf904565bbbd5a9c7e4d329fdbb2101b5d2f4655bd91223a5610b0c03efd'}
d=Path('/root/amadeus-m119l')
d.mkdir(mode=0o700)
with zipfile.ZipFile(p) as a:
 assert set(a.namelist())==expected.keys()
 for name,h in expected.items():
  raw=a.read(name)
  assert hashlib.sha256(raw).hexdigest()==h
  with (d/name).open('xb') as f:f.write(raw)
print('Six exact frozen inputs staged in a new local Linux directory.')
PY

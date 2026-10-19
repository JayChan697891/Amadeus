"""Generate environment-verified exact pins and runtime license inventory."""
from importlib import metadata
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
import json

root = Path(__file__).resolve().parents[1]
def closure(initial):
    found={}
    pending=[(name,set()) for name in initial]
    explored=set()
    while pending:
        name, extras=pending.pop()
        key=(canonicalize_name(name),tuple(sorted(extras)))
        if key in explored: continue
        explored.add(key)
        dist=metadata.distribution(name)
        found[canonicalize_name(dist.metadata['Name'])]=dist
        for text in dist.requires or []:
            req=Requirement(text)
            if req.marker and not any(req.marker.evaluate({'extra':ex}) for ex in extras|{''}): continue
            pending.append((req.name,set(req.extras)))
    return found

runtime=closure(['mcp','fastapi','uvicorn','pydantic'])
development=closure([*runtime,'httpx','pytest','pytest-asyncio','ruff','mypy','build','pip-licenses'])
for filename, packages in [('requirements-lock.txt',runtime),('requirements-dev-lock.txt',development)]:
    lines=['# Resolved and tested on Windows / CPython 3.14, 2026-10-19.',
           '# Exact environment snapshot, not a cross-platform resolver lock.',
           '# pywin32 is Windows-only; other platforms still require CI verification.']
    for name,dist in sorted(packages.items()):
        marker='; sys_platform == "win32"' if name=='pywin32' else ''
        lines.append(f'{dist.metadata["Name"]}=={dist.version}{marker}')
    (root/filename).write_text('\n'.join(lines)+'\n',encoding='utf-8')

table=['# Third-party runtime dependencies', '',
       'Inventory from installed package metadata and bundled license files. Generated 2026-10-19.',
       'This covers the runtime transitive dependency closure, including Windows-only pywin32.',
       'Project code is MIT; dependencies retain their own licenses. See THIRD-PARTY-NOTICES.txt.', '',
       '| Package | Version | Declared license |', '|---|---|---|']
notices=[]
inventory=[]
for name,dist in sorted(runtime.items()):
    expression=dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See bundled notices'
    classifiers=[c.split(' :: ')[-1] for c in dist.metadata.get_all('Classifier',[]) if c.startswith('License ::')]
    if len(expression)>160: expression=', '.join(classifiers) or 'See bundled notices'
    expression=' '.join(expression.split()).replace('|',' / ')
    license_files=[file for file in dist.files or [] if any(part.lower().startswith(('license','copying','notice')) for part in file.parts)]
    table.append(f'| {dist.metadata["Name"]} | {dist.version} | {expression} |')
    inventory.append({'name':name,'version':dist.version,'license':expression,'bundled_license_files':len(license_files)})
    for file in license_files:
        path=dist.locate_file(file)
        if path.is_file():
            notices.append(f'===== {name} {dist.version} / {file.name} =====\n'+path.read_text(encoding='utf-8',errors='replace'))
(root/'docs/THIRD-PARTY-LICENSES.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
(root/'docs/THIRD-PARTY-NOTICES.txt').write_text('\n\n'.join(notices),encoding='utf-8')
(root/'docs/dependency-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
print(json.dumps({'runtime_packages':len(runtime),'development_packages':len(development),'missing_bundled_licenses':[x['name'] for x in inventory if not x['bundled_license_files']]}))

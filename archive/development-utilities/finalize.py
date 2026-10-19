"""Verify portable source inventory, render its tree, and inspect build contents."""
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
files=sorted(set(subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines()+['docs/FILE-TREE.md','.gitattributes']))
for filename in files:
    path=root/filename
    assert not any(part in {'.venv','work','.git','__pycache__'} for part in path.relative_to(root).parts),filename
    assert not re.search(r'\.(db|sqlite)(-|$)',filename),filename
    if not path.is_file(): continue
    data=path.read_bytes()
    assert not re.search(rb'sk-(?:proj-|ant-)[A-Za-z0-9_-]{20,}',data),filename
    assert b'C:\\Users\\JayChan' not in data,filename
for file in ['docs/pytest-results.xml','docs/pytest-python312.xml']:
    tree=ET.parse(root/file)
    suite=tree.find('testsuite')
    assert suite.attrib['tests']=='64' and suite.attrib['failures']=='0' and suite.attrib['errors']=='0',file
nodes={}
for path in files:
    node=nodes
    for part in path.split('/'):
        node=node.setdefault(part,{})
lines=['# Source file tree','','Portable source inventory. Excludes local environments, scratch data, caches, .git and built packages.','','```text','AgentSync/']
def render(node,prefix=''):
    items=sorted(node.items())
    for i,(name,child) in enumerate(items):
        last=i==len(items)-1
        lines.append(prefix+('└── ' if last else '├── ')+name+('/' if child else ''))
        render(child,prefix+('    ' if last else '│   '))
render(nodes)
lines.extend(['```',''])
(root/'docs/FILE-TREE.md').write_text('\n'.join(lines),encoding='utf-8')
print(f'Portable inventory checked: {len(files)} files; both final JUnit reports 64/64 green.')

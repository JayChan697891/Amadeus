from pathlib import Path
import hashlib
import json
import tarfile
import xml.etree.ElementTree as ET
import zipfile

root=Path(__file__).resolve().parents[1]
out=root.parent
for name in ('pytest-m2-followup.xml','pytest-m2-followup-python312.xml'):
    suite=ET.parse(root/'docs'/name).find('testsuite')
    assert suite.attrib['tests']=='92'
    assert suite.attrib['errors']==suite.attrib['failures']==suite.attrib['skipped']=='0'
    assert 'hostname' not in suite.attrib
confirmation=json.loads((root/'docs/desktop-connection-confirmation.json').read_text(encoding='utf-8'))
assert confirmation['desktop_mcp_connected'] and not confirmation['automated_desktop_ui_tested']
registration=json.loads((root/'docs/codex-registration-probe.json').read_text(encoding='utf-8'))
assert registration['runtime_status']=='connected' and len(registration['tools'])==11
assert not registration['command_line_configuration_override'] and not registration['thread_configuration_override']
assert registration['inference_turns']==0
wheel=out/'agentsync_local-0.1.0a2-py3-none-any.whl'
normalize=lambda content:content.replace(b'\r\n',b'\n').rstrip()
with zipfile.ZipFile(wheel) as archive:
    modules=[name for name in archive.namelist() if name.startswith('agentsync/') and name.endswith('.py')]
    installed=root/'work/clean312/Lib/site-packages'
    assert all(normalize(archive.read(name))==normalize((installed/name).read_bytes()) for name in modules)
with zipfile.ZipFile(out/'AgentSync-v0.1.0a2-source.zip') as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        assert not any(part in {'.git','.venv','work','__pycache__','.env'} for part in Path(name).parts)
        assert not name.endswith('.db')
    assert 'AgentSync/docs/desktop-connection-confirmation.json' in archive.namelist()
with tarfile.open(out/'agentsync_local-0.1.0a2.tar.gz') as archive:
    assert any(name.endswith('/examples/mcp_clients/install_codex.py') for name in archive.getnames())
files=[wheel,out/'AgentSync-v0.1.0a2-source.zip',out/'agentsync_local-0.1.0a2.tar.gz']
hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
(out/'AgentSync-v0.1.0a2-SHA256SUMS.txt').write_text('\n'.join(value+'  '+name for name,value in hashes.items())+'\n',encoding='utf-8')
print(json.dumps({'a2_test_reports':'92/92 on both interpreters','tested_modules_match_final_wheel':len(modules),'portable_archives_verified':True,'desktop_confirmation':'direct user report','hashes':hashes}))

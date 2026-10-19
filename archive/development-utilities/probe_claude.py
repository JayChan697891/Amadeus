"""Isolated official Claude Code MCP health check; no model prompt or credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
binary=Path(os.environ['APPDATA'])/'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
config_dir=root/'work/claude-isolated-config'
config_dir.mkdir(parents=True,exist_ok=True)
env={key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ['ANTHROPIC','OPENAI','API_KEY','AUTH_TOKEN'])}
env.update(CLAUDE_CONFIG_DIR=str(config_dir),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
server={'command':sys.executable,'args':['-m','agentsync','--data-dir',str(root/'work/claude-native-state'),'mcp']}
def run(args):
    return subprocess.run([str(binary),*args],env=env,cwd=root/'work',capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
run(['mcp','remove','--scope','user','agentsync'])
added=run(['mcp','add-json','--scope','user','agentsync',json.dumps(server)])
assert added.returncode==0,added.stderr
listed=run(['mcp','list'])
print(listed.stdout)
assert listed.returncode==0,listed.stderr
connected='Connected' in listed.stdout or 'connected' in listed.stdout
report={'host':'installed Claude Code CLI','model_prompts':0,'isolated_config':True,'credentials_provided':False,'health_check_connected':connected,'tool_calls_tested':False,'desktop_ui_tested':False}
(root/'docs/claude-host-probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
assert connected,listed.stdout

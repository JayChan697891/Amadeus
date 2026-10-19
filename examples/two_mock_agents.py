"""Usage: python examples/two_mock_agents.py ABSOLUTE_DEMO_DIRECTORY."""

import json
import sys

from agentsync.cli import run_demo

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Pass an absolute demo state directory")
    print(json.dumps(run_demo(sys.argv[1]), ensure_ascii=False, indent=2))

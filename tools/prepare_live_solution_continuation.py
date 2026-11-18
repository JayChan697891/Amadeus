"""Render the reviewed two-call controller for one fresh a119 solution.py fixture."""

import argparse
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs/acceptance/evidence"
R2 = EVIDENCE / "durable-demo-a117"
OUTPUT = Path("D:/agentsync-debug/strategy-demo/interrupted-a119-solution-20261116")
OLD_GUEST = "/root/amadeus-interrupted-a117-r2-20261116"
GUEST = "/root/amadeus-interrupted-a119-solution-20261116"
PACKAGE = "/root/amadeus-m119l"
PYTHON = PACKAGE + "/w/bin/python"
VERSION = "0.3.0a119"
COMMIT = "4be51345d5b8846da58d79df5b8567619e9acfed"
WHEEL_SHA = "cbcf38bfe80a61510cbc95fb2a7112173222a7b6bb03404a324e52e23d237c31"
MEMBERS_SHA = "545b490670bdbb0f73a74fb13dca77cf9b875c38f350d5a1b2f0f4fdb3b829a7"
MEMBERS = EVIDENCE / "core-preview-a119/windows/run/runtime-members.json"
TEMPLATES = {
    "prepare.py": "f85dc33940a0e39c68a09d7faf3b5ea627895131b75cea17d935229e49f77cd0",
    "live.py": "a2914736eb8e2a9e8d9eaba7a433c4d2d584493822df920c0cb7c41e43d52d18",
    "cleanup.py": "8d95d045a5fe36c5a50fcf8d348d806437a4992b595fd03e166046ad28bfde8a",
    "run-stage.py": "acf2750d4f5df5d74b403302f6054ff3e7a7da2263fb70975afa75f1f6cef783",
    "receiver-decision.py": "f951a49c1647f72413a94eb5dce697512b5c53d81b0cfd8e38a3649143ab450e",
}
OLD_PLAN = "c975d7abad85b122d6850d5ca78eded295e2c4ecfb18b96fe5c66add3a4cf2c7"
OLD_READY = "2a8095c1e013b3d43cd4631ad626eeb8a8e0a1320e1c89471e93e3eaa635c324"
OLD_PRODUCER = "b78f84c53cbdef2eb055719b53f4a7d163bded339ada208745136c2f05d4b00d"
GOAL = (
    "Implement solution.py with total(values) returning the sum of the JSON array of integers. "
    "The script must read one JSON array per stdin line and write one JSON integer per stdout "
    "line, in order, with no extra output."
)
BOUNDARY = "Do not use tools, read or modify files, or run code."
CONTINUATION = GOAL + " Finish the pinned unfinished function. " + BOUNDARY
JSON_LINES = """
import json
import sys

for line in sys.stdin:
    print(json.dumps(total(json.loads(line))), flush=True)
"""
PARTIAL = (
    "def total(values):\n    # Host-known partial checkpoint.\n    raise NotImplementedError\n"
)
REFERENCE = "def total(values):\n    return sum(values)\n" + JSON_LINES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError(f"Unexpected input digest for {path.name}")
    return data


def substitute(source, changes):
    for previous, replacement in changes:
        if source.count(previous) != 1:
            raise ValueError(f"Unexpected template layout for {previous[:60]!r}")
        source = source.replace(previous, replacement)
    return source


def template(name):
    source = checked(R2 / "interrupted-live-r2/drivers" / (name + ".txt"), TEMPLATES[name])
    return (
        source.decode()
        .replace(OLD_GUEST, GUEST)
        .replace("/root/amadeus-demo-a117-sdist-r1/installed/bin/python", PYTHON)
    )


def preparation():
    source = template("prepare.py")
    source = source.replace("SDIST_SHA", "WHEEL_SHA").replace("sdist_sha256", "wheel_sha256")
    return substitute(
        source,
        (
            ('Path("/root/amadeus-demo-a117-sdist-r1")', f"Path({PACKAGE!r})"),
            ('"fc27f15f47fa92ed5edcd764a573c1d84a68c107"', repr(COMMIT)),
            ('"b78a748bea7bbc4885f1d4448ba02e15fa335e6b78e4f189a37b165d0326f672"', repr(WHEEL_SHA)),
            (
                '"f76a68a40ee5f675d69dd903d6d8975ab19f71c5e5a4f6e129aa710964b1c06a"',
                repr(MEMBERS_SHA),
            ),
            (
                '"agentsync_local-0.3.0a117.tar.gz"',
                json.dumps(f"agentsync_local-{VERSION}-py3-none-any.whl"),
            ),
            ('(PACKAGE / "installed")', '(PACKAGE / "w")'),
            ('"0.3.0a117"', json.dumps(VERSION)),
            (
                'WAVE_REQUEST = "interrupted-add-producer-wave"',
                'WAVE_REQUEST = "interrupted-solution-producer-wave"',
            ),
            (
                'CHECKPOINT_REQUEST = "host-known-add-progress"',
                'CHECKPOINT_REQUEST = "host-known-solution-progress"',
            ),
            ('PATHS = ("add.py",)', 'PATHS = ("solution.py",)'),
            (
                'GOAL = "Implement add(a, b) in add.py so that it returns a + b for two integers."',
                f"GOAL = {GOAL!r}",
            ),
            (
                'PARTIAL = "def add(a, b):\\n    # Host-known partial checkpoint.\\n    raise NotImplementedError\\n"',
                f"PARTIAL = {PARTIAL + JSON_LINES!r}\nREFERENCE_SHA256 = {sha(REFERENCE.encode())!r}",
            ),
            (
                "Isolated add(a, b) continuation fixture.",
                "Isolated solution.py JSON-lines continuation fixture.",
            ),
            ('"Interrupted add proposal"', '"Interrupted JSON-lines solution proposal"'),
            ('"Interrupted add " + who', '"Interrupted JSON-lines solution " + who'),
            (
                '    for who in ("producer", "receiver"):\n        member =',
                '    for who in ("producer", "receiver", "stager", "reviewer"):\n        member =',
            ),
            ('"roles": ["worker"],', '"roles": ["reviewer" if who == "reviewer" else "worker"],'),
            ('"producer-add"', '"producer-solution"'),
            ('"Follow up on the add proposal"', '"Follow up on the JSON-lines solution proposal"'),
            ('"dependent-add"', '"dependent-solution"'),
            ('"snapshot-add"', '"snapshot-solution"'),
            ('"worktree-add"', '"worktree-solution"'),
            (
                '"continuation_instruction": CONTINUATION,',
                '"continuation_instruction": CONTINUATION,\n'
                '            "reference_solution_sha256": REFERENCE_SHA256,',
            ),
        ),
    )


def write(name, data):
    if name.endswith(".py"):
        compile(data, name, "exec")
    with (OUTPUT / name).open("xb") as stream:
        stream.write(data)


def write_json(name, value):
    write(name, (json.dumps(value, indent=2) + "\n").encode())


def render(recovery=False):
    common = {
        "prepare.py": preparation().encode(),
        "private_capture.py": checked(
            R2 / "interrupted-preparation/private_capture.py.txt",
            "d9548ad05fab5c91ffb3f7f17ed86169881968af0d8b5a763f22af0ed18646d7",
        ),
        "interrupt_parent.py": checked(
            R2 / "interrupted-controller/interrupt_parent.py.txt",
            "6b7af496d936d0cb66f92d986427540c3bae29ed2e8af051ddc05ccbff3e1343",
        ),
        "runtime-members.json": checked(MEMBERS, MEMBERS_SHA),
        "cleanup.py": substitute(
            template("cleanup.py"),
            (
                ('"amadeus-interrupted-a117-r2-auth"', '"amadeus-interrupted-a119-solution-auth"'),
                ('        "cleanup.py",', '        "cleanup.py",\n        "verify.py",'),
                (
                    "def main():\n",
                    'def main():\n    if not __debug__:\n        raise SystemExit("Do not disable checks.")\n',
                ),
            ),
        ).encode(),
        "verify.py": (REPO / "tools/run_live_solution_verification.py").read_bytes(),
        "reference-solution.py.txt": REFERENCE.encode(),
    }
    if recovery:
        common["cleanup.py"] = (
            substitute(
                common["cleanup.py"].decode(),
                (('        "verify.py",', '        "verify.py",\n        "recovery.py",'),),
            )
            .replace(
                "amadeus-interrupted-a119-solution-auth", "amadeus-m122-composed-recovery-auth"
            )
            .encode()
        )
        common["verify.py"] = (
            substitute(
                common["verify.py"].decode(),
                (
                    ('"/root/amadeus-interrupted-a119-solution-20261116"', repr(GUEST)),
                    (
                        "def publication(live, core, state, request, grant):\n",
                        "def publication(live, core, state, request, grant):\n    import recovery\n",
                    ),
                    (
                        '        "continuation_plan_sha256": original["plan_sha256"],',
                        '        "continuation_plan_sha256": original["plan_sha256"],\n'
                        "        **recovery.approval_binding(live, original),",
                    ),
                ),
            )
            .replace("one a119 continuation", "one recovered a122 continuation")
            .encode()
        )
        common["recovery.py"] = (REPO / "tools/run_live_solution_recovery.py").read_bytes()
        common["scope.json"] = (
            json.dumps(
                {
                    "runtime_commit": COMMIT,
                    "wheel_sha256": WHEEL_SHA,
                    "runtime_manifest_sha256": MEMBERS_SHA,
                    "model_execution": "NOT RUN",
                    "maximum_subscription_calls": 2,
                    "extra_fees_allowed": False,
                    "automatic_retry": False,
                    "candidate_execution": "NOT RUN; exact new approval required after preview",
                },
                indent=2,
            )
            + "\n"
        ).encode()
    OUTPUT.mkdir(exist_ok=False)
    for name, data in common.items():
        write(name, data)
    write_json("prepared-inputs.json", {name: sha(data) for name, data in common.items()})


def bind(recovery=False):
    inputs = json.loads((OUTPUT / "prepared-inputs.json").read_bytes())
    prepared = (
        "prepare.py",
        "private_capture.py",
        "interrupt_parent.py",
        "runtime-members.json",
        "cleanup.py",
        "verify.py",
    ) + (("recovery.py",) if recovery else ())
    for name in prepared:
        checked(OUTPUT / name, inputs[name])
    plan_file, ready_file = (
        (OUTPUT / name).read_bytes() for name in ("plan.json", "readiness.json")
    )
    plan, ready = json.loads(plan_file), json.loads(ready_file)
    producer = plan["producer_plan"]["plan_sha256"]
    assert re.fullmatch("[0-9a-f]{64}", producer) and ready["producer_plan_sha256"] == producer
    assert plan["runtime_commit"] == COMMIT and plan["wheel_sha256"] == WHEEL_SHA
    assert plan["runtime_members"] == 97 and plan["proposed_model_call_limit"] == 2
    assert (
        plan["automatic_retry"] is False
        and ready["selection_sha256"] == plan["producer_plan"]["selection_sha256"]
    )
    assert plan["helper_sha256"] == {
        name: inputs[name] for name in ("prepare.py", "private_capture.py", "runtime-members.json")
    }
    assert plan["host_checkpoint"]["files"] == [
        {"path": "solution.py", "content": PARTIAL + JSON_LINES}
    ]
    assert plan["host_checkpoint"]["origin"] == "host_known_partial_source"
    assert plan["host_checkpoint"]["model_authorship"] is False
    assert plan["continuation_instruction"] == CONTINUATION
    assert plan["model_calls"] == ready["model_calls"] == 0
    assert plan["external_auth_copies"] == ready["external_auth_copies"] == 0
    assert ready["private_home_empty"] is True

    live = (
        template("live.py")
        .replace("a117 producer", "a119 producer")
        .replace("fixed add.py", "fixed solution.py")
    )
    live = substitute(
        live,
        (
            (TEMPLATES["prepare.py"], inputs["prepare.py"]),
            ("f76a68a40ee5f675d69dd903d6d8975ab19f71c5e5a4f6e129aa710964b1c06a", MEMBERS_SHA),
            (OLD_PLAN, sha(plan_file)),
            (OLD_READY, sha(ready_file)),
            (OLD_PRODUCER, producer),
            (
                '"Continue the interrupted add(a, b) proposal"',
                '"Continue the interrupted JSON-lines solution proposal"',
            ),
            (
                '{"path": "add.py", "content": prep.PARTIAL}',
                '{"path": prep.PATHS[0], "content": prep.PARTIAL}',
            ),
            (
                'set(PREPARED) | {"live.py", "cleanup.py"}',
                'set(PREPARED) | {"live.py", "cleanup.py", "verify.py"}',
            ),
            (
                "def main():\n",
                'def main():\n    if not __debug__:\n        raise SystemExit("Do not disable checks.")\n',
            ),
        ),
    )
    runner = substitute(template("run-stage.py"), ((OLD_PLAN, sha(plan_file)),)).replace(
        "R2", "a119"
    )
    receiver = substitute(
        template("receiver-decision.py"),
        (
            (
                "def main():\n",
                'def main():\n    if not __debug__:\n        raise SystemExit("Do not disable checks.")\n',
            ),
            (
                "        original = json.loads((BASE / 'plan.json').read_bytes())['producer_plan']",
                "        original_raw = (BASE / 'plan.json').read_bytes()\n"
                f"        assert hashlib.sha256(original_raw).hexdigest() == {sha(plan_file)!r}\n"
                "        original = json.loads(original_raw)['producer_plan']",
            ),
            (
                "        assert payload['stdin_text'].startswith('Implement add(a, b) in add.py so that it returns a + b for two integers. Finish the pinned unfinished function. Do not use tools, read or modify files, or run code.\\n')",
                f"        assert approved['plan']['instruction_sha256'] == {sha(json.dumps(CONTINUATION).encode())!r}\n"
                f"        assert payload['stdin_text'].startswith({(CONTINUATION + chr(10))!r})",
            ),
            ("['add.py']", "['solution.py']"),
        ),
    )
    if recovery:
        live, runner = recovery_sources(live, runner)
    write("live.py", live.encode())
    write("run-stage.py", runner.encode())
    write("receiver-decision.py", receiver.encode())
    write_json(
        "live-authorization.template.json",
        {
            "schema_version": 1,
            "producer_plan_sha256": producer,
            "files": {
                name: sha((OUTPUT / name).read_bytes())
                for name in (
                    "prepare.py",
                    "private_capture.py",
                    "runtime-members.json",
                    "plan.json",
                    "readiness.json",
                    "interrupt_parent.py",
                    "live.py",
                    "cleanup.py",
                    "verify.py",
                    *(("recovery.py",) if recovery else ()),
                )
            },
            "expires_at": None,
            "max_model_calls": 2,
            "existing_subscription_only": True,
            "owner_confirmed_zero_credits_and_auto_recharge_off": None,
            "api_key_allowed": False,
            "producer_owned_parent_interruption_allowed": True,
            "retry_allowed": False,
            "temporary_auth_destination": GUEST + "/private-home/auth.json",
        },
    )


def recovery_sources(live, runner):
    live = substitute(
        live,
        (
            (
                'set(PREPARED) | {"live.py", "cleanup.py", "verify.py"}',
                'set(PREPARED) | {"live.py", "cleanup.py", "verify.py", "recovery.py"}',
            ),
            (
                "    async def authority(review):\n        nonlocal authorizations, capture, approved_review",
                "    checkpoint = None\n"
                "    async def retain_before_exit(result):\n"
                "        nonlocal checkpoint\n"
                "        checkpoint = await diagnostics(\n"
                '            "receiver", relay, state, task_id, capture, authorizations,\n'
                "            approved_review, None, asdict(result),\n"
                "        )\n"
                "        return checkpoint\n\n"
                "    async def authority(review):\n        nonlocal authorizations, capture, approved_review",
            ),
            (
                "        outcome = await flow.run_once(\n            request,",
                "        import recovery\n"
                "        outcome = await recovery.run_to_checkpoint(\n"
                "            sys.modules[__name__], flow, request, core, state, entry, retain_before_exit,",
            ),
            (
                "            execution_budget_seconds=230,\n        )",
                "            execution_budget_seconds=230,\n        )\n"
                '        raise AssertionError("Receiver did not stop at the reviewed checkpoint.")',
            ),
            (
                '        observed, schema_exact, snapshot, final_turn, meta = await diagnostics(\n            "receiver",',
                '        observed, schema_exact, snapshot, final_turn, meta = checkpoint or await diagnostics(\n            "receiver",',
            ),
            (
                '    stages.add_parser("replay")',
                '    stages.add_parser("recover")\n    stages.add_parser("replay")',
            ),
            (
                "        return asyncio.run(replay(grant))",
                '        if args.stage == "recover":\n'
                "            import recovery\n"
                "            return recovery.recover(sys.modules[__name__], grant)\n"
                "        return asyncio.run(replay(grant))",
            ),
        ),
    )
    runner = substitute(
        runner,
        (
            (
                '    stages.add_parser("replay")',
                '    stages.add_parser("recover")\n    stages.add_parser("replay")',
            ),
            (
                "    stage = args.stage\n",
                "    stage = args.stage\n"
                '    if stage == "recover":\n'
                '        exited = json.loads((BASE / "continue-once-result.json").read_bytes())\n'
                '        if exited.get("status") != "terminal" or exited.get("exit_code") != 73:\n'
                '            parser.error("The exact receiver controller exit 73 was not observed.")\n',
            ),
        ),
    )
    return live.replace("a119 producer", "a122 producer"), runner.replace("a119", "a122")


def configure_recovery():
    global OUTPUT, GUEST, PACKAGE, PYTHON, VERSION, COMMIT, WHEEL_SHA, MEMBERS_SHA, MEMBERS
    OUTPUT = Path("D:/agentsync-debug/m122-composed-recovery")
    GUEST = "/root/amadeus-m122-composed-recovery"
    PACKAGE = "/root/amadeus-m122l"
    PYTHON = PACKAGE + "/w/bin/python"
    VERSION = "0.3.0a122"
    COMMIT = "5232e9e8bd33a949f7ffdc68410cd614a297af66"
    WHEEL_SHA = "8fd24c89b8b21a0b9e1aa5564fe130846af7a9516bb2c7cd2faf114ccc2c08ab"
    MEMBERS_SHA = "cdc35d4b827a54bbe8e47e69e994216f1a1d401ae5ca522fc4f041162cf48e2c"
    MEMBERS = EVIDENCE / "core-preview-a122/windows/runtime-members.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if not __debug__:
        parser.error("Do not disable checks.")
    parser.add_argument("action", choices=("render", "bind"))
    parser.add_argument("--composed-recovery", action="store_true")
    args = parser.parse_args()
    if args.composed_recovery:
        configure_recovery()
    (render if args.action == "render" else bind)(args.composed_recovery)


if __name__ == "__main__":
    main()

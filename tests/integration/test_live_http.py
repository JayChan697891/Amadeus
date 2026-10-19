"""Real TCP transport and a fresh interpreter after server shutdown."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time

import httpx


def test_real_loopback_http_and_process_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    data_dir = tmp_path / "state"
    token = secrets.token_urlsafe(32)
    env = {**os.environ, "AGENTSYNC_HTTP_TOKEN": token}
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agentsync",
                "--data-dir",
                str(data_dir),
                "serve",
                "--port",
                str(port),
            ],
            env=env,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False
            ) as client:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        response = client.get("/health")
                        response.raise_for_status()
                        break
                    except httpx.HTTPError:
                        if time.monotonic() > deadline or process.poll() is not None:
                            raise AssertionError("Local HTTP server failed to start") from None
                        time.sleep(0.05)
                assert response.json()["status"] == "ok"
                assert client.post("/v1/create_project", json={}).status_code == 401

                def call(operation, payload):
                    response = client.post(
                        f"/v1/{operation}",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    response.raise_for_status()
                    envelope = response.json()
                    assert envelope["ok"], envelope
                    return envelope["data"]

                project = call("create_project", {"name": "Live HTTP", "root_path": str(tmp_path)})
                session = call("register_agent", {**project, "name": "HTTP agent"})
                auth = {
                    "project_id": project["project_id"],
                    "session_id": session["session_id"],
                    "session_token": session["session_token"],
                }
                task = call(
                    "create_task",
                    {**auth, "title": "Survive process exit", "request_id": "tcp-create"},
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
    # Credentials pass over stdin, not command-line arguments or saved reports.
    code = (
        "import json,sys; from agentsync.sdk import AgentSyncClient; "
        "p=json.load(sys.stdin); r=AgentSyncClient(p['data_dir']).call('list_tasks',**p['auth']); "
        "assert r['ok']; print(json.dumps([t['id'] for t in r['data']['tasks']]))"
    )
    reopened = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps({"data_dir": str(data_dir), "auth": auth}),
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    assert task["id"] in json.loads(reopened.stdout)

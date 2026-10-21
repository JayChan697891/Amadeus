"""Trusted developer transport to the dedicated loopback debug VM, not an AgentSync API."""

import argparse
import hashlib
import json
import time
from pathlib import Path, PurePosixPath

import paramiko


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("D:/agentsync-debug"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--log", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--script", type=Path, help="Trusted owner-authored guest setup/test script")
    group.add_argument("--upload", nargs=2, metavar=("LOCAL", "GUEST"))
    group.add_argument("--download", nargs=2, metavar=("GUEST", "LOCAL"))
    args = parser.parse_args()
    root = args.root.resolve()
    if root.drive.upper() != "D:":
        raise SystemExit("Debug runtime must remain on the authorized D: drive")
    client = paramiko.SSHClient()
    hosts = root / "vm" / "known_hosts"
    if hosts.exists():
        client.load_host_keys(str(hosts))
    # First-contact trust is restricted to the newly created local-only VM.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        "127.0.0.1",
        port=22222,
        username="root",
        key_filename=str(root / "vm" / "debug_ed25519"),
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        auth_timeout=15,
        banner_timeout=15,
    )
    client.save_host_keys(str(hosts))
    key = client.get_transport().get_remote_server_key()
    (root / "vm" / "ssh-host-identity.json").write_text(
        json.dumps({"type": key.get_name(), "sha256": hashlib.sha256(key.asbytes()).hexdigest()}),
        encoding="utf-8",
    )
    try:
        if args.upload or args.download:
            pair = args.upload or args.download
            remote = pair[1] if args.upload else pair[0]
            remote_path = PurePosixPath(remote)
            if not remote_path.is_relative_to("/root") or ".." in remote_path.parts:
                raise SystemExit("Transfers are restricted to the disposable guest /root tree")
            with client.open_sftp() as sftp:
                if args.upload:
                    sftp.put(pair[0], remote)
                else:
                    sftp.get(remote, pair[1])
            print("Transferred one debug fixture/evidence file")
            return
        script = args.script.read_bytes().replace(b"\r\n", b"\n")
        if len(script) > 1024 * 1024:
            raise SystemExit("Trusted script exceeds the developer transport limit")
        channel = client.get_transport().open_session(timeout=10)
        channel.set_combine_stderr(True)
        channel.exec_command("sh -s")
        channel.sendall(script)
        channel.shutdown_write()
        output = bytearray()
        deadline = time.monotonic() + args.timeout
        while True:
            while channel.recv_ready():
                output.extend(channel.recv(65536))
                if len(output) > 16 * 1024 * 1024:
                    raise SystemExit("Trusted debug output exceeded processing limit")
                if args.log:
                    args.log.write_bytes(output)
            if channel.exit_status_ready() and not channel.recv_ready():
                break
            if time.monotonic() > deadline:
                raise SystemExit("Trusted guest command timed out; inspect guest before retrying")
            time.sleep(0.1)
        code = channel.recv_exit_status()
        if args.log:
            args.log.write_bytes(output)
        else:
            print(output.decode("utf-8", errors="replace"))
        raise SystemExit(code)
    finally:
        client.close()


if __name__ == "__main__":
    main()

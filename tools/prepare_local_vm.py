"""Create a private NoCloud seed for the owner's D-drive debug VM; never upload its output."""

import argparse
import io
import json
import secrets
from pathlib import Path

import pycdlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from passlib.hash import sha512_crypt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    key_path = root / "debug_ed25519"
    if key_path.exists() or (root / "seed.iso").exists():
        raise SystemExit("Refusing to replace an existing VM key or seed")
    key = Ed25519PrivateKey.generate()
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
    )
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode("ascii")
    )
    # An unknowable random password hash avoids Alpine locked-account rejection.
    # Password SSH remains disabled; neither password nor hash enters public evidence.
    password_hash = sha512_crypt.hash(secrets.token_urlsafe(48))
    user_data = "\n".join(
        [
            "#cloud-config",
            "disable_root: false",
            "ssh_pwauth: false",
            "users:",
            "  - default",
            "  - name: root",
            "    lock_passwd: false",
            "    hashed_passwd: " + json.dumps(password_hash),
            "    ssh_authorized_keys:",
            "      - " + public,
            "package_update: true",
            "packages: [docker, git, python3, py3-pip, py3-virtualenv]",
            "runcmd:",
            # Some Alpine images omit cloud-init's package-install module.
            "  - [sh, -ec, 'apk update && apk add docker git python3 py3-pip py3-virtualenv']",
            "  - [rc-update, add, cgroups, boot]",
            "  - [rc-service, cgroups, start]",
            "  - [rc-update, add, docker, default]",
            "  - [rc-service, docker, start]",
            "  - [sh, -ec, 'docker info >/dev/null && echo ready > /root/agentsync-debug-ready']",
            "",
        ]
    ).encode("utf-8")
    metadata = (
        "instance-id: agentsync-debug-"
        + secrets.token_hex(12)
        + "\nlocal-hostname: agentsync-debug\n"
    ).encode("ascii")
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident="CIDATA", rock_ridge="1.09")
    for name, data in (("user-data", user_data), ("meta-data", metadata)):
        iso.add_fp(
            io.BytesIO(data),
            len(data),
            iso_path="/" + name.upper().replace("-", "_") + ";1",
            rr_name=name,
            joliet_path="/" + name,
        )
    iso.write(str(root / "seed.iso"))
    iso.close()
    print("Created private VM key/NoCloud seed; do not upload these runtime files")


if __name__ == "__main__":
    main()

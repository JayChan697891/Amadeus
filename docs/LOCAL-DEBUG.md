# Local debug environment on D:

Owner instruction, 2026-10-20: GitHub is storage only. Do not dispatch Actions,
remote checks or benchmarks. Keep automatic workflow triggers disabled and use
`[skip ci]` when saving code/evidence. Source remains in F:/syuc; this dedicated
debug runtime, dependencies, caches, fixtures and VM disks live in D:/agentsync-debug.

## Actual environment

- Windows CPython3.14.6 virtual environment: D:/agentsync-debug/venv.
- Portable QEMU11.1.0, published Windows build20260811, SHA512 checked against the
  publisher; no system installer was run.
- Official Alpine3.24.2 cloud-init VM image, SHA512 checked against Alpine's index.
- A private QCOW2 overlay on D: was expanded to16GiB; the downloaded base is retained.
-3GiB guest RAM, one virtual CPU, WHPX acceleration with kernel-irqchip=off.
- Linux6.18.54-0-virt, Python3.14.7, Docker29.8.2, cgroupv2 and builtin seccomp.
- Only127.0.0.1 ports22222(SSH) and22223(QMP) are bound. No host directory is shared.

The first WHPX default interrupt configuration intermittently stopped serving SSH.
The explicit userspace interrupt controller and one vCPU configuration was then
booted and used successfully for package installation, transfer and real tests.
No WSL/Hyper-V Windows feature was enabled or host restart requested.
These observations describe this machine, not universal Windows compatibility.

## Recreate and operate

Install the optional tools into a D: virtual environment using
tools/local-debug-requirements.txt. Obtain and verify the QEMU installer and Alpine
QCOW2 through the primary references below. Extract QEMU locally with7-Zip rather
than running its installer. Create an overlay with qemu-img using explicit qcow2
backing format, then resize the overlay to16GiB.

`tools/prepare_local_vm.py D:/agentsync-debug/vm` creates a fresh private NoCloud
seed and dedicated key; it refuses to replace existing inputs. Protect the key with
owner-only Windows ACLs. The seed disables password SSH and uses an unknowable random
password hash to avoid Alpine locked-account key rejection. It starts cgroups and
Docker, and marks readiness only after Docker info succeeds. The current image's
package-install cloud-init module was absent, so explicit apk setup was required;
the seed now includes that fallback in runcmd.

`tools/start_local_vm.ps1` launches the owned VM hidden and refuses occupied ports.
It never stops an existing process. `tools/local_vm_exec.py` is a trusted developer
SSH transport fixed to localhost22222, independent of normal user SSH configuration.
It normalizes script newlines and pins the first observed key in the dedicated VM
directory. It is not an AgentSync API or a command interface for model submissions.
Uploads/downloads are limited to the disposable guest /root tree. Owner-authored
setup scripts may install packages there; candidate source is still executed only
by the inspected Docker verifier, never by the Windows/Linux test driver.

Keep image preparation separate from candidate execution: preload the official
Python image, record its full local ID and registry digest, and pass only the ID
to the verifier with --pull=never. A missing backend or security control must fail,
without host execution fallback. Tests and benchmarks are local only.

## Evidence and private runtime

D:/agentsync-debug/evidence holds environment manifests, sanitized logs, JUnit and
real Docker result JSON. Source/wheel/sdist must use distinct interpreters. Actual
Docker JSON is grouped by the SHA256 of sys.prefix so runs cannot overwrite another
installation's evidence. Copy only sanitized evidence and reproducible scripts into
the repository. Record the exact source SHA/tree, module hashes and artifact hashes;
a pre-freeze local success is not certification of a later commit.

Never upload vm/debug_ed25519, vm/seed.iso, guest disks, credentials or raw private
configuration. Their locations are recorded without their contents. The runtime can
be recreated from verified public images and freshly generated credentials. Stop
the VM through QMP only after checking the saved PID/executable/disk identity; do
not stop unrelated processes or delete arbitrary paths.

## First actual reproduction and repair

This local VM reproduced all14 original isolation_mismatch failures. Safe results
showed only the environment predicate false, with every other isolation check true,
execution_started=false and cleanup_confirmed=true.

A trusted fixed container probe established that Docker Config.Env retains bare
GPG_KEY/PYTHON_VERSION/PYTHON_SHA256 deletion markers, while actual process os.environ
does not contain them. The verifier now recognizes only unique expected markers
derived from already-validated image metadata. All valued entries must still equal
the four fixed runtime settings; unknown/duplicate markers or additional values
fail. A fixed container bootstrap independently checks the actual environment
before reading candidate source. The isolation probe also checks metadata is absent.

The root-user guest fixture placed its canary under/root, where Python3.12 Path.exists
raises PermissionError for the container user. The fixed test uses an exclusively
created host temporary file under traversable/tmp, without sharing it with the
container. A leak would expose its existence, rather than hide behind parent access.
All14 actual cases then passed in9.80s. Final commit/package verification remains a
separate gate; this is not complete M5, actual agent relay or formal release approval.

## Primary references

- [QEMU Windows downloads](https://www.qemu.org/download/#windows)
- [Windows publisher and SHA512](https://qemu.weilnetz.de/w64/)
- [Alpine cloud image variants](https://alpinelinux.org/cloud/)
- [Cloud-init NoCloud](https://docs.cloud-init.io/en/latest/reference/datasources/nocloud.html)
- [Alpine Docker](https://wiki.alpinelinux.org/wiki/Docker)
- [QEMU WHPX support and limitations](https://www.qemu.org/docs/master/system/whpx.html)

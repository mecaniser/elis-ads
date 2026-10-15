#!/usr/bin/env python3
"""Build an Intel wheel from pinned sources; output requires independent review."""
from __future__ import annotations

import hashlib
import base64
import csv
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

SOURCES = {
    "cryptography": {
        "version": "50.0.2",
        "url": "https://files.pythonhosted.org/packages/9d/af/182eb91b0df3fe75c4d9f26fe70684569566745f6ba7e5c9c73a862c5252/cryptography-50.0.2.tar.gz",
        "sha256": "7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5",
    },
    "openssl": {
        "version": "3.5.9",
        "url": "https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz",
        "sha256": "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str, cwd: Path | None = None, env=None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, flush=True)
    result.check_returncode()
    return result.stdout.strip()


def verify_load_commands(commands: str) -> None:
    minimums = re.findall(r"minos\s+(\d+\.\d+(?:\.\d+)?)", commands)
    if not minimums or any(tuple(map(int, value.split('.'))) > (11, 0, 0) for value in minimums):
        raise SystemExit("Wheel native module exceeds macOS 11 minimum")
    for block in commands.split("Load command "):
        # LC_ID_DYLIB declares this binary's own identity, not a loaded dependency.
        if not re.search(r"\bcmd LC_(?!ID_DYLIB\b)\w*DYLIB\b", block):
            continue
        name = re.search(r"\bname (.+) \(offset \d+\)", block)
        if not name or not name.group(1).startswith(("/usr/lib/", "/System/Library/")) or any(
            segment in {".", ".."} for segment in name.group(1).split("/")
        ):
            raise SystemExit("Wheel links a non-system dynamic library")


def main() -> None:
    if platform.system() != "Darwin" or platform.machine() != "x86_64" or sys.version_info[:2] != (3, 11):
        raise SystemExit("Build requires native Intel macOS and CPython 3.11")
    root = Path(__file__).resolve().parents[1]
    output = root / "intel-wheel-output"
    output.mkdir(exist_ok=False)
    evidence = {"schema_version": "1.0.0", "sources": SOURCES, "source_commit": run("git", "rev-parse", "HEAD"),
                "workflow_run_id": os.environ.get("GITHUB_RUN_ID"), "runner_os": platform.mac_ver()[0],
                "architecture": platform.machine(), "python": platform.python_version(),
                "rust": run("rustc", "--version"), "compiler": run("clang", "--version"),
                "build_tools_lock_sha256": sha(root / "control-plane/vendor/intel-build-tools.lock")}
    with tempfile.TemporaryDirectory(prefix="intel-crypto-") as temporary:
        work = Path(temporary)
        for name, source in SOURCES.items():
            archive = work / f"{name}.tar.gz"
            with urllib.request.urlopen(source["url"]) as response:
                archive.write_bytes(response.read())
            if sha(archive) != source["sha256"]:
                raise SystemExit(f"Source hash mismatch: {name}")
            with tarfile.open(archive) as bundle:
                bundle.extractall(work, filter="data")
        openssl = work / "openssl-3.5.9"
        prefix = work / "openssl-install"
        env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "11.0"}
        run("./Configure", "darwin64-x86_64-cc", "no-shared", "no-module", f"--prefix={prefix}", cwd=openssl, env=env)
        run("make", "-j3", cwd=openssl, env=env)
        run("make", "test", cwd=openssl, env=env)
        run("make", "install_sw", cwd=openssl, env=env)
        shutil.copy2(openssl / "LICENSE.txt", output / "OPENSSL-LICENSE.txt")
        source = work / "cryptography-50.0.2"
        evidence["cargo_lock_sha256"] = sha(source / "Cargo.lock")
        env.update(OPENSSL_DIR=str(prefix), OPENSSL_STATIC="1", OPENSSL_NO_VENDOR="1")
        run("maturin", "build", "--release", "--locked", "--interpreter", sys.executable, "--out", str(output), cwd=source, env=env)
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1 or not wheels[0].name.endswith("macosx_11_0_x86_64.whl"):
            raise SystemExit("Unexpected wheel identity/platform")
        wheel = wheels[0]
        # Preserve the statically linked OpenSSL notice inside the distributed
        # wheel and update RECORD, without changing any executable payload.
        with zipfile.ZipFile(wheel) as bundle:
            contents = {name: bundle.read(name) for name in bundle.namelist()}
        dist_info = "cryptography-50.0.2.dist-info"
        license_path = f"{dist_info}/licenses/OPENSSL-LICENSE.txt"
        contents[license_path] = (output / "OPENSSL-LICENSE.txt").read_bytes()
        record_path = f"{dist_info}/RECORD"
        record = io.StringIO()
        writer = csv.writer(record, lineterminator="\n")
        for name, data in sorted(contents.items()):
            if name != record_path:
                digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                writer.writerow([name, f"sha256={digest}", len(data)])
        writer.writerow([record_path, "", ""])
        contents[record_path] = record.getvalue().encode()
        with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, data in sorted(contents.items()):
                bundle.writestr(name, data)
        metadata = contents[f"{dist_info}/METADATA"].decode()
        tags = contents[f"{dist_info}/WHEEL"].decode()
        if "\nVersion: 50.0.2\n" not in metadata or "Tag: cp311-abi3-macosx_11_0_x86_64" not in tags:
            raise SystemExit("Wheel metadata must support CPython 3.11 and 3.12 through abi3")
        with zipfile.ZipFile(wheel) as bundle:
            bundle.extractall(work / "wheel")
        binaries = list((work / "wheel").rglob("*.so"))
        if not binaries:
            raise SystemExit("Wheel has no native module")
        for binary in binaries:
            if run("lipo", "-archs", str(binary)) != "x86_64":
                raise SystemExit("Wheel contains a non-Intel native module")
            commands = run("otool", "-l", str(binary))
            verify_load_commands(commands)
            run("otool", "-L", str(binary))
        run(sys.executable, "-m", "pip", "install", "--no-deps", str(wheel))
        run(sys.executable, "-c", "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; from cryptography.hazmat.backends.openssl.backend import backend; k=Ed25519PrivateKey.generate(); k.public_key().verify(k.sign(b'ci'),b'ci'); assert backend.openssl_version_text().startswith('OpenSSL 3.5.9'); print(backend.openssl_version_text())")
        evidence["wheel"] = {"filename": wheel.name, "sha256": sha(wheel)}
        evidence["openssl_license_sha256"] = sha(output / "OPENSSL-LICENSE.txt")
        evidence["verification"] = {"openssl_tests": "passed", "ed25519_sign_verify": "passed", "static_openssl": True}
        (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

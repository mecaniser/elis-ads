#!/usr/bin/env python3
"""Host-only Tart controller. One ephemeral non-admin job per discarded VM."""
import fcntl
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

REPO = 'mecaniser/elis-ads'
BASE = 'owned-macos15-base'
WORKER = 'ci-ads-macos-1'
LABEL = 'owned-macos15'
ROOT = Path.home() / 'Library/Application Support/Ads Mac CI'
TART = str(Path.home() / 'Library/Application Support/Owned CI Tools/tart.app/Contents/MacOS/tart')
KEY = Path.home() / 'Library/Application Support/Owned CI Tools/management_ed25519'
STOP = threading.Event()
LOG = logging.getLogger('owned-mac-ci')


def command(args, data=None, check=True, timeout=120):
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if check and result.returncode:
        # Tokens are passed on stdin and response bodies never enter logs.
        raise RuntimeError(f'{args[0]} failed with exit {result.returncode}')
    return result


def api(path, method='GET'):
    return json.loads(command(['gh', 'api', path, '--method', method]).stdout or '{}')


def guest(ip, script, data=None, check=True, timeout=120):
    return command(['ssh', '-F', '/dev/null', '-i', str(KEY), '-o', 'IdentitiesOnly=yes',
                    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                    '-o', 'StrictHostKeyChecking=yes', '-o', f'HostKeyAlias={BASE}',
                    '-o', f'UserKnownHostsFile="{KEY.parent / (BASE + ".hostkey")}"',
                    f'ciadmin@{ip}', script], data=data, check=check, timeout=timeout)


def destroy(name):
    if name != WORKER:
        raise ValueError('Refusing to remove an unmanaged VM')
    names = command([TART, 'list', '--source', 'local', '--quiet']).stdout.splitlines()
    if name in names:
        command([TART, 'stop', name], check=False)
        command([TART, 'delete', name])
    for runner in api(f'repos/{REPO}/actions/runners')['runners']:
        if runner['name'] == name:
            api(f'repos/{REPO}/actions/runners/{runner["id"]}', 'DELETE')


def register(ip):
    # Fail closed before issuing any token or running repository code.
    guest(ip, 'sudo /usr/local/sbin/ci-preflight')
    token = api(f'repos/{REPO}/actions/runners/registration-token', 'POST')['token']
    configure = ("sudo -u admin env HOME=/Users/admin /bin/bash -c "
                 "'cd /Users/admin/actions-runner && export ACTIONS_RUNNER_INPUT_TOKEN=\"$(cat)\" && "
                 f"./config.sh --unattended --ephemeral --url https://github.com/{REPO} "
                 f"--name {WORKER} --labels {LABEL} --work _work'")
    guest(ip, configure, data=token)
    guest(ip, 'sudo launchctl bootstrap system /usr/local/etc-ci-runner.plist')


def cycle():
    destroy(WORKER)
    command([TART, 'clone', BASE, WORKER], timeout=180)
    with (ROOT / 'vm.log').open('w') as output:
        process = subprocess.Popen([TART, 'run', WORKER, '--no-graphics', '--no-audio',
                                    '--no-usb-accessories', '--no-clipboard'],
                                   stdout=output, stderr=output)
        try:
            ip = ''
            deadline = time.monotonic() + 240
            while not STOP.wait(5) and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('VM exited before registration')
                ip = command([TART, 'ip', WORKER], check=False, timeout=15).stdout.strip()
                if ip and guest(ip, 'true', check=False).returncode == 0:
                    break
            else:
                raise RuntimeError('Guest readiness timed out')
            register(ip)
            LOG.info('%s listening in a fresh VM', WORKER)
            started = time.monotonic()
            while not STOP.wait(15):
                if process.poll() is not None:
                    raise RuntimeError('VM exited during job')
                runners = api(f'repos/{REPO}/actions/runners')['runners']
                if not any(r['name'] == WORKER for r in runners):
                    LOG.info('Ephemeral registration removed; discarding VM')
                    return
                if time.monotonic() - started > 7200:
                    raise RuntimeError('Two-hour lifetime exceeded')
        finally:
            command([TART, 'stop', WORKER], check=False)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=30)


def main():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    with (ROOT / 'supervisor.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        while not STOP.is_set():
            try:
                cycle()
            except Exception as error:
                LOG.error('%s', error)
            finally:
                try:
                    destroy(WORKER)
                except Exception as error:
                    LOG.error('Cleanup failed: %s', error)
            STOP.wait(15)


if __name__ == '__main__':
    main()

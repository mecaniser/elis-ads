# Persistent local CI for elis-ads

Linux jobs use disposable Ubuntu 24.04 x86-64 QEMU guests on owned Apple Silicon
hardware, labelled `owned-linux-x64`. Apple Silicon jobs use disposable macOS 15
Tart guests, labelled `owned-macos15`. Windows and Intel macOS tests remain hosted by explicit
owner choice. All matrix entries, check commands, triggers and failure semantics
are retained. Previously inactive workflows remain inactive.

## Linux

Provision a pristine mount-free `ci-x64-base` from `base.yaml`, then run:

```sh
limactl shell ci-x64-base sudo bash < provision.sh
limactl shell ci-x64-base sudo tee /etc/nftables.conf < network.nft >/dev/null
limactl shell ci-x64-base sudo systemctl enable --now nftables
limactl shell ci-x64-base sudo nft list table inet ci_isolation
limactl stop ci-x64-base
python3 install.py
```

No repository jobs run in the base. Workers have no host mounts, forwarded agents,
host Docker socket or sudo. Rootless Docker and root-owned nft rules block private
networks and IPv6. Public DNS is explicit and Lima host-resolver DNAT is disabled. Container UID 1001 gets
a default ACL only on the disposable `_work` directory so existing non-root Docker
jobs can write their bind mounts. Package installation occurs during provisioning;
workflow package checks verify the preinstalled dependencies without sudo.

## macOS

Use Tart 2.41.0 from its official release, with a pristine macOS 15 ARM64 base.
Set 4 CPUs and 4096 MB memory. Run with `--no-graphics --no-audio
--no-usb-accessories --no-clipboard`, with no host shares. Before registration:

1. Generate the host-only management Ed25519 key outside all checkouts.
2. Run `macos/provision.sh` as root in the pristine guest, passing its public key.
3. Run `macos/python-toolcache.sh` as root; install poppler as the job account.
4. Pin the guest SSH public host key as `owned-macos15-base.hostkey` beside the
   management key, prefixed with the base name (SSH HostKeyAlias).
5. Verify `ci-preflight`, public HTTPS, blocked private access, denied job sudo,
   and the same checks after a guest reboot. Stop the pristine base.
6. Install the reviewed controller with `python3 macos/install.py`.

The image's `admin` user is demoted to a non-admin job account. `ciadmin` accepts
only the host management key; no private key or host GitHub credential enters a
guest. Root-owned pf rules permit public egress, gateway DNS/DHCP and management
SSH responses while denying other private traffic and IPv6. SSH forwarding is
disabled. Preinstalled Python versions avoid giving setup-python installer sudo.
Each job uses an ephemeral registration and is followed by complete VM deletion.
The supervisor refuses registration when isolation preflight fails.

## Operation and verification

Install reviewed supervisor copies outside checkouts. macOS LaunchAgents use
KeepAlive and RunAtLoad; the host must be powered, online and logged in after
FileVault unlock. An unavailable host queues jobs without bypassing checks.
Repository settings require approval for all external contributors. Never put
host credentials in a guest or use a repository-controlled host script.

Run `python3 test_supervisor.py` and `python3 macos/test_supervisor.py` for negative
controller tests, and actionlint for workflow syntax. Acceptance additionally
requires real GitHub jobs on each platform; static checks alone are insufficient.
Rollback is a focused PR restoring runner routing, retaining every check.
Subscriptions, spending limits, required checks and production hosting are unchanged.

## Provisioned macOS image provenance

Initial upstream image: `ghcr.io/cirruslabs/macos-sequoia-base@sha256:eee659985b01e4df2a6c0754bd8d25e54969933c43fdcd4edef8bea337b3d354`.
Tart 2.41.0 official archive SHA-256:
`07faafc77acc668fcfb2fbe97811622567fb89c650db401a470f72e7c4ddc560`.
Guest hardening and tool provisioning are applied before making the stopped base.

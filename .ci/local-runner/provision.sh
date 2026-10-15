#!/bin/bash
# Run as root in a fresh, mount-free Ubuntu 24.04 x86-64 Lima base VM.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git jq build-essential python3 python3-venv \
  acl libpango-1.0-0 libpangoft2-1.0-0 gh poppler-utils fonts-noto-color-emoji uidmap dbus-user-session slirp4netns fuse-overlayfs nftables unzip zip libicu74 libssl-dev zlib1g-dev
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf '%s\n' 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable' > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli docker-ce-rootless-extras
systemctl disable --now docker.service docker.socket
# Ubuntu's AppArmor userns restriction otherwise prevents rootless Docker.
# Only the isolated guest changes; runner still has no sudo/capabilities.
printf 'kernel.apparmor_restrict_unprivileged_userns=0\n' > /etc/sysctl.d/90-ci-rootless.conf
sysctl --system
useradd --create-home --shell /bin/bash --uid 1100 runner
loginctl enable-linger runner
mkdir -p /opt/hostedtoolcache /opt/actions-runner
chown runner:runner /opt/hostedtoolcache /opt/actions-runner
curl -fsSL https://nodejs.org/dist/v20.20.1/node-v20.20.1-linux-x64.tar.xz -o /tmp/node.tar.xz
curl -fsSL https://nodejs.org/dist/v20.20.1/SHASUMS256.txt -o /tmp/node-shasums
(cd /tmp; grep ' node-v20.20.1-linux-x64.tar.xz$' node-shasums | sed 's/node-v20.20.1-linux-x64.tar.xz/node.tar.xz/' | sha256sum -c -)
tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
curl -fsSL https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz -o /tmp/runner.tar.gz
echo 'af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32  /tmp/runner.tar.gz' | sha256sum -c -
tar -xzf /tmp/runner.tar.gz -C /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh
chown -R runner:runner /opt/actions-runner
# Same OS dependency installer as the workflow, provisioned with root only here.
npx --yes playwright@1.58.2 install-deps chromium
runuser -u runner -- env HOME=/home/runner XDG_RUNTIME_DIR=/run/user/1100 dockerd-rootless-setuptool.sh install
runuser -u runner -- env HOME=/home/runner XDG_RUNTIME_DIR=/run/user/1100 systemctl --user enable docker
cat > /etc/systemd/system/db-ci-runner.service <<'UNIT'
[Unit]
Description=Disposable DieselBridge GitHub Actions worker
After=network-online.target nftables.service user@1100.service
Requires=nftables.service
[Service]
User=runner
Group=runner
WorkingDirectory=/opt/actions-runner
Environment=HOME=/home/runner
Environment=XDG_RUNTIME_DIR=/run/user/1100
Environment=DOCKER_HOST=unix:///run/user/1100/docker.sock
Environment=RUNNER_TOOL_CACHE=/opt/hostedtoolcache
ExecStart=/opt/actions-runner/run.sh
KillMode=control-group
TimeoutStopSec=20
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
# Not enabled: the supervisor starts it only after configuring a fresh clone.
rm -f /tmp/node.tar.xz /tmp/runner.tar.gz /tmp/node-shasums

# gstack's non-root container UID 1001 maps into runner's subordinate range.
# Grant only that identity access to disposable job workspaces, never host files.
mkdir -p /opt/actions-runner/_work
chown runner:runner /opt/actions-runner/_work
subuid=$(awk -F: '$1=="runner"{print $2}' /etc/subuid)
setfacl -m u:$((subuid+1000)):rwx,d:u:$((subuid+1000)):rwx /opt/actions-runner/_work

# Avoid QEMU TCG's intermittent IO-APIC timer boot panic on Apple Silicon.
printf '%s\n' 'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT noapic"' > /etc/default/grub.d/99-ci-timer.cfg
update-grub

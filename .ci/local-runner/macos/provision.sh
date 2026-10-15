#!/bin/bash
# Root, in a pristine Tart macOS guest only. First argument: management public key.
set -euo pipefail
[[ $(uname -s) == Darwin && $(id -u) == 0 ]]
[[ -d /Users/admin && ! -d /Users/sergio_m1_promax ]]
key=${1:?management public key required}
gateway=$(/sbin/route -n get default | awk '/gateway:/{print $2}')
[[ $gateway =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
# SSH management has its own identity; no private key is installed in the guest.
dscl . -create /Users/ciadmin
dscl . -create /Users/ciadmin UserShell /bin/bash
dscl . -create /Users/ciadmin UniqueID 550
dscl . -create /Users/ciadmin PrimaryGroupID 20
dscl . -create /Users/ciadmin NFSHomeDirectory /Users/ciadmin
dscl . -create /Users/ciadmin RealName 'CI Management'
dscl . -create /Users/ciadmin Password '*'
dseditgroup -o edit -a ciadmin -t user com.apple.access_ssh
mkdir -p /Users/ciadmin/.ssh
printf '%s\n' "$key" > /Users/ciadmin/.ssh/authorized_keys
chown -R ciadmin:staff /Users/ciadmin
chmod 700 /Users/ciadmin /Users/ciadmin/.ssh
chmod 600 /Users/ciadmin/.ssh/authorized_keys
mkdir -p /etc/sudoers.d
printf 'ciadmin ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/ci-management
chmod 440 /etc/sudoers.d/ci-management
# The image's default account becomes the non-admin job account.
if id -Gn admin | tr ' ' '\n' | grep -qx admin; then
  dseditgroup -o edit -d admin -t user admin
fi
# Image-specific passwordless entries are removed; retain root/default admin policy.
for file in /etc/sudoers /etc/sudoers.d/*; do
  [[ -f "$file" ]] || continue
  sed -i '' '/^[[:space:]]*admin[[:space:]].*NOPASSWD/d' "$file"
  chmod 440 "$file"
done
visudo -c
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/000-ci.conf <<'SSH'
AllowUsers ciadmin
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding no
SSH
/usr/sbin/sshd -t
mkdir -p /Users/admin/actions-runner /Users/runner/hostedtoolcache
chown -R admin:staff /Users/admin/actions-runner /Users/runner
curl -fsSL https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-osx-arm64-2.338.0.tar.gz -o /tmp/runner.tar.gz
echo 'df4cebda25c86a886ed204e49fee63f5c2e7cec5f447b5c98440a826bbdf9df2  /tmp/runner.tar.gz' | shasum -a 256 -c -
tar -xzf /tmp/runner.tar.gz -C /Users/admin/actions-runner
chown -R admin:staff /Users/admin/actions-runner
rm /tmp/runner.tar.gz
cat > /etc/pf.conf <<PF
set block-policy drop
set skip on lo0
table <ci_private> const { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 198.18.0.0/15, 224.0.0.0/4, 240.0.0.0/4 }
block in all
block out quick inet6 all
pass in quick inet proto tcp from $gateway to any port 22 flags any keep state
pass out quick inet proto { udp tcp } to $gateway port 53 keep state
pass out quick inet proto udp from any port 68 to { $gateway 255.255.255.255 } port 67 keep state
block out quick inet to <ci_private>
pass out inet all keep state
PF
chmod 600 /etc/pf.conf
mkdir -p /usr/local/sbin
cat > /usr/local/sbin/ci-firewall <<'FIREWALL'
#!/bin/bash
set -eu
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
/sbin/pfctl -f /etc/pf.conf
/sbin/pfctl -e || /sbin/pfctl -s info | grep -q 'Status: Enabled'
FIREWALL
chmod 755 /usr/local/sbin/ci-firewall
cat > /Library/LaunchDaemons/com.owned-ci.firewall.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>
<key>Label</key><string>com.owned-ci.firewall</string>
<key>ProgramArguments</key><array><string>/usr/local/sbin/ci-firewall</string></array>
<key>RunAtLoad</key><true/>
</dict></plist>
PLIST
cat > /Library/LaunchDaemons/com.owned-ci.runner.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>
<key>Label</key><string>com.owned-ci.runner</string>
<key>UserName</key><string>admin</string>
<key>WorkingDirectory</key><string>/Users/admin/actions-runner</string>
<key>ProgramArguments</key><array><string>/Users/admin/actions-runner/run.sh</string></array>
<key>EnvironmentVariables</key><dict>
<key>HOME</key><string>/Users/admin</string>
<key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
<key>RUNNER_TOOL_CACHE</key><string>/Users/runner/hostedtoolcache</string>
</dict>
<key>RunAtLoad</key><true/>
<key>StandardOutPath</key><string>/Users/admin/runner.log</string>
<key>StandardErrorPath</key><string>/Users/admin/runner.log</string>
</dict></plist>
PLIST
# Do NOT load the runner in a base. Disable automatic launch until host registers a clone.
# Keep its definition outside LaunchDaemons so rebooting a base cannot load it.
mv /Library/LaunchDaemons/com.owned-ci.runner.plist /usr/local/etc-ci-runner.plist
cat > /usr/local/sbin/ci-preflight <<'PREFLIGHT'
#!/bin/bash
set -euo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
! id -Gn admin | tr ' ' '\n' | grep -qx admin
! sudo -n -u admin sudo -n true 2>/dev/null
/sbin/pfctl -s info | grep -q 'Status: Enabled'
/sbin/pfctl -sr | grep -q 'block drop out quick inet from any to <ci_private>'
[[ $(stat -f %Su /etc/pf.conf) == root ]]
! mount | grep -q virtiofs
PREFLIGHT
chown root:wheel /usr/local /usr/local/sbin /usr/local/sbin/ci-preflight /usr/local/sbin/ci-firewall
chmod 755 /usr/local /usr/local/sbin /usr/local/sbin/ci-preflight /usr/local/sbin/ci-firewall
chown root:wheel /Library/LaunchDaemons/com.owned-ci.firewall.plist /usr/local/etc-ci-runner.plist
chmod 644 /Library/LaunchDaemons/com.owned-ci.firewall.plist /usr/local/etc-ci-runner.plist
/usr/local/sbin/ci-firewall
/usr/local/sbin/ci-preflight

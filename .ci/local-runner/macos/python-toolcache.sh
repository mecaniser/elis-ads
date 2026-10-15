#!/bin/bash
set -euo pipefail
ds_users=/Users
job_home=$(dscl . -read "$ds_users/admin" NFSHomeDirectory | cut -d ' ' -f 2-)
export RUNNER_TOOL_CACHE="$(dirname "$job_home")/runner/hostedtoolcache"
mkdir -p /tmp/ci-python-3.11.9
cd /tmp/ci-python-3.11.9
curl -fsSL 'https://github.com/actions/python-versions/releases/download/3.11.9-9947079978/python-3.11.9-darwin-arm64.tar.gz' -o python.tgz
tar -xzf python.tgz
bash setup.sh
mkdir -p /tmp/ci-python-3.12.10
cd /tmp/ci-python-3.12.10
curl -fsSL 'https://github.com/actions/python-versions/releases/download/3.12.10-14343898437/python-3.12.10-darwin-arm64.tar.gz' -o python.tgz
tar -xzf python.tgz
bash setup.sh
chown -R admin:staff "$RUNNER_TOOL_CACHE" /Library/Frameworks/Python.framework
rm -rf /tmp/ci-python-3.11.9 /tmp/ci-python-3.12.10

#!/bin/bash
# Provision only in a pristine Linux base before accepting repository jobs.
set -euo pipefail
[[ $(id -u) == 0 && $(uname -m) == x86_64 ]]
export RUNNER_TOOL_CACHE=/opt/hostedtoolcache
export AGENT_TOOLSDIRECTORY=$RUNNER_TOOL_CACHE
install_python() {
  local release=$1 digest=$2 version=${1%-*}
  local staging
  staging=$(mktemp -d)
  curl -fsSL "https://github.com/actions/python-versions/releases/download/$release/python-$version-linux-24.04-x64.tar.gz" -o "$staging/python.tgz"
  echo "$digest  $staging/python.tgz" | sha256sum -c -
  tar -xzf "$staging/python.tgz" -C "$staging"
  rm "$staging/python.tgz"
  (cd "$staging" && bash setup.sh)
  rm -rf "$staging"
}
install_python 3.11.17-36876195594 ae713815fe406a06f1691856f697a0b1e58b3e986f44e62f0cd0bca2424f1aac
install_python 3.12.15-36805895057 fcb672b0437c2d8df5565b7cc250b2b0d7455e2b8d6a4a107cfa6f2efe4f7ed8
chown -R runner:runner "$RUNNER_TOOL_CACHE"
# setup-python still selects the workflow's requested version and verifies its cache.
# Refresh these official artifacts when workflows need a newer Python release.

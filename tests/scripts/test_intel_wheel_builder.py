"""Reject unsupported deployment targets and non-system linked libraries."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "intel_builder", Path(__file__).resolve().parents[2] / "scripts/build_intel_cryptography.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def commands(kind="LC_LOAD_DYLIB", library="/usr/lib/libSystem.B.dylib", minimum="11.0"):
    return f"""Load command 0
      cmd LC_BUILD_VERSION
    minos {minimum}
Load command 1
      cmd LC_ID_DYLIB
     name @rpath/cryptography.hazmat.bindings._rust.abi3.so (offset 24)
Load command 2
      cmd {kind}
     name {library} (offset 24)
"""


def test_self_identity_is_not_an_external_dependency():
    builder.verify_load_commands(commands())


@pytest.mark.parametrize("kind", ["LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB", "LC_LAZY_LOAD_DYLIB", "LC_LOAD_UPWARD_DYLIB"])
def test_non_system_dependencies_rejected(kind):
    with pytest.raises(SystemExit, match="non-system"):
        builder.verify_load_commands(commands(kind, "@rpath/libcrypto.3.dylib"))


@pytest.mark.parametrize("minimum", ["11.0.1", "11.1", "12.0", "unknown"])
def test_unsupported_or_missing_minimum_rejected(minimum):
    with pytest.raises(SystemExit, match="minimum"):
        builder.verify_load_commands(commands(minimum=minimum))


def test_missing_dependency_name_rejected():
    with pytest.raises(SystemExit, match="non-system"):
        builder.verify_load_commands(commands().replace("name /usr/lib/libSystem.B.dylib", "invalid"))


@pytest.mark.parametrize("library", ["/usr/lib/../../tmp/libcrypto.dylib", "/System/Library/../libcrypto.dylib", "/usr/lib/./libcrypto.dylib"])
def test_system_library_prefix_cannot_hide_traversal(library):
    with pytest.raises(SystemExit, match="non-system"):
        builder.verify_load_commands(commands(library=library))

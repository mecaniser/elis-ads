# Reviewed Intel Cryptography wheel

Cryptography 50 no longer publishes Intel macOS wheels. ELIS Ads retains its
Intel macOS CPython 3.11 and 3.12 installer lanes by building Cryptography
50.0.2 from the publisher's source with statically linked OpenSSL 3.5.9.

`scripts/build_intel_cryptography.py` runs on the hosted Intel runner. It verifies
the source archive hashes, uses hash-locked Python build tools and Cargo's locked
dependency graph, runs the OpenSSL tests, and checks the wheel's Intel architecture,
macOS 11 deployment target, abi3 tag, system-only dynamic links, and Ed25519 signing.
The wheel includes the OpenSSL license and an updated wheel RECORD.

The generated wheel and build evidence require independent review before being
added to the dependency inventory. The verifier pins the reviewed build evidence
digest, the exact wheel bytes, and an immutable commit URL in this repository.
Only that Intel Cryptography artifact may use the additional wheel source. Every
other dependency must retain its publisher artifact URL. Installation still uses
`--require-hashes --only-binary=:all:`; source builds never happen at installation.

The existing native installer matrix, complete test suite, vulnerability audits,
and release verification remain required. A successful wheel build alone does not
establish release readiness. The Pillow security update sets the managed Linux
minimum to glibc 2.27; macOS 11 and Windows platform coverage remain unchanged.

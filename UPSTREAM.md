# Upstream synchronization

Elis Ads remains connected to the canonical Claude Ads repository:

- Upstream: `https://github.com/AgriciDaniel/claude-ads.git`
- Elis fork: `https://github.com/mecaniser/elis-ads.git`
- Default branch: `main`

The Elis-specific layer should stay small and focused. Internal package names,
schemas, commands, and product contracts should not be renamed unless there is
a compelling compatibility reason.

## Manual sync

```bash
git remote add upstream https://github.com/AgriciDaniel/claude-ads.git
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
```

Once Elis-specific commits exist, a fast-forward may no longer be possible.
Create a synchronization branch instead:

```bash
git fetch upstream
git switch -c sync/upstream-YYYY-MM-DD
git merge upstream/main
git push -u origin sync/upstream-YYYY-MM-DD
```

Review upstream changes, resolve any conflicts, run the full test suite, and
merge through a pull request. The scheduled workflow in
`.github/workflows/upstream-sync.yml` automates this branch-and-PR approach.

## Current baseline

The Elis Ads fork was synchronized to upstream commit
`669c7608ecb50dd95c941a71fa3ca0a1c0e40512` (Claude Ads v2.0.1) before the
Elis-specific customization was added.

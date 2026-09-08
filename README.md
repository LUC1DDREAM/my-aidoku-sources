# PanelNest legacy compatibility publisher

Canonical source code and website: https://github.com/LUC1DDREAM/panelnest and https://luc1ddream.github.io/panelnest/.

Keep installed lists using https://luc1ddream.github.io/my-aidoku-sources/experimental/index.min.json. This repository serves complete static copies, not JSON-to-HTML redirects. Source IDs, package metadata, versioned packages and icons are preserved. No source adapters are built here.

The scheduled workflow pulls the canonical public Pages checksum manifest once, downloads its complete tree without redirects, then verifies exact file membership, SHA256 hashes, catalog IDs, experimental status, package metadata, embedded icons and WASM headers. A mixed deployment, missing frozen asset, changed frozen asset or failed request prevents deployment; the last successful Pages deployment stays in place. It uses no cross-repository token. SHA256 provides consistency, not an independent authenticity guarantee. Only PanelNest's own public HTTPS Pages origin is fetched. Reviewed checkout and Pages actions are pinned.

Schedule: every six hours, at minute 23. GitHub schedules can be delayed or disabled by inactivity; this is not instantaneous synchronization. Watch failed Actions notifications and manually dispatch as needed. Future source additions require a reviewed allowlist update. Future versions must retain initial versioned packages/icons in the canonical artifact or mirroring fails closed. Current immutable seed assets are pinned, but later version history is not automatically archived.

## Rollback and operation

- Normal synchronization: `gh workflow run compatibility.yml -R LUC1DDREAM/my-aidoku-sources -f seed=false`
- Frozen endpoint rollback: `gh workflow run compatibility.yml -R LUC1DDREAM/my-aidoku-sources -f seed=true`
- Monitor the exact run with `gh run watch RUN_ID -R LUC1DDREAM/my-aidoku-sources --exit-status`, then independently fetch the exact JSON, packages and icons. A green job is not an HTTP verification.
- Frozen seed: canonical source commit `1b46c5e30d6d7137155dd9f77b00389111ed00ea`, successful Pages run `34219517886`; 34 files. Root checksum-manifest SHA256 `b0561dd8073e96dfe642c6a050a00eeab3d37d0e9b3336918c7accc2bc2176aa`.
- Local checks: `python -m unittest -v`; `python mirror.py --seed --output rollback-test` (output must not exist).

The frozen snapshot includes old canonical website links by design; normal synchronization uses the new canonical links while relative resources still work at either path. Root catalog remains intentionally empty; experimental catalog contains six sources and is not a supported release. Native iPhone refresh/import behavior requires device testing.

Do not casually rename/delete this repository: it owns the installed legacy URL. Reversing the original rename is separate coordinated maintenance, not the artifact rollback above. Recreating this name intentionally replaces GitHub's repository/git redirect. Attribution and source licenses are retained in the canonical repository history and `licenses/`/source directories there.

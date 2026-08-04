# Nixzle's English Aidoku Sources

Public, unofficial English and multilingual source packages for Aidoku. The main list follows the active Aidoku community catalog so removed, unmaintained packages do not continue to appear healthy.

## Add to Aidoku

Paste this URL into Aidoku under Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/index.min.json`

The normal list contains the currently maintained packages. Comix and Read Comics Online use maintained builds and require Aidoku 0.8.4 or newer.

### ReadComicOnline replacement

The original ReadComicOnline websites no longer resolve, so that broken entry is hidden from the maintained list. Install **Read Comics Online** (with spaces) instead. It is a separate website, so bookmarks from the original source do not migrate automatically.

If Read Comics Online gets stuck on Cloudflare verification, update Aidoku to 0.8.4 or newer, clear the network cache under Aidoku's Advanced settings, and retry. **BatCave** is included as a second comics fallback; open its source settings and use **Verify BatCave Access** if it fails to load.

Older packages are preserved in a separate legacy list, but many no longer work because their websites or parsers changed:

`https://nixzle.github.io/aidoku-sources/legacy/index.min.json`

Package provenance and SHA-256 checksums are recorded in each catalog's `inventory.json` and `CHECKSUMS.sha256`.

Packages marked for personal download only by their maintainer are intentionally excluded from this public repository. External sources are unofficial and are not affiliated with Aidoku or the websites they access.

#!/usr/bin/env python3
"""Refresh Nixzle's public Aidoku source list from redistributable upstreams."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Nixzle-Aidoku-Sources-Updater/1.0"
TIMEOUT_SECONDS = 45
ENGLISH_MARKERS = {"en", "all", "multi"}
SOURCE_PREFERENCES: dict[str, str] = {}
ACTIVE_REPOSITORY = "Aidoku-Community/sources"

# Only repositories whose packages may be publicly redistributed are included.
# Higher priority wins when two repositories publish the same source or website.
UPSTREAMS = (
    {
        "name": "Aidoku-Community/sources",
        "index": "https://aidoku-community.github.io/sources/index.min.json",
        "asset_base": "https://aidoku-community.github.io/sources/",
        "priority": 300,
        "license": "MIT OR Apache-2.0",
    },
    {
        "name": "tachibana-shin/aidoku-sources-next",
        "index": "https://raw.githubusercontent.com/tachibana-shin/aidoku-sources-next/gh-pages/index.min.json",
        "asset_base": "https://raw.githubusercontent.com/tachibana-shin/aidoku-sources-next/gh-pages/",
        "priority": 200,
        "license": "MIT OR Apache-2.0",
    },
    {
        "name": "tachibana-shin/aidoku-community-sources",
        "index": "https://raw.githubusercontent.com/tachibana-shin/aidoku-community-sources/gh-pages/index.min.json",
        "asset_base": "https://raw.githubusercontent.com/tachibana-shin/aidoku-community-sources/gh-pages/",
        "priority": 100,
        "license": "MIT OR Apache-2.0",
    },
)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read()


def fetch_json(url: str):
    return json.loads(fetch_bytes(url).decode("utf-8-sig"))


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def entry_languages(entry: dict) -> list[str]:
    return [str(value) for value in as_list(entry.get("languages", entry.get("lang")))]


def is_english_entry(entry: dict) -> bool:
    source_id = str(entry.get("id", "")).casefold()
    return (
        source_id.startswith(("en.", "multi."))
        and any(language.casefold() in ENGLISH_MARKERS for language in entry_languages(entry))
    )


def normalized_url_key(urls: list[str]) -> str | None:
    for value in urls:
        try:
            parsed = urlparse(value)
            if not parsed.hostname:
                continue
            host = parsed.hostname.casefold()
            if host.startswith("www."):
                host = host[4:]
            path = parsed.path.rstrip("/").casefold()
            return f"{host}{path}"
        except ValueError:
            continue
    return None


def package_url(upstream: dict, entry: dict) -> str:
    reference = entry.get("downloadURL")
    if reference:
        return urljoin(upstream["asset_base"], str(reference))
    filename = entry.get("file")
    if filename:
        return urljoin(upstream["asset_base"], f"sources/{filename}")
    raise ValueError(f"Source {entry.get('id', '<unknown>')} has no package reference")


def read_package(package: bytes, label: str) -> tuple[dict, bytes]:
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = {name.casefold(): name for name in archive.namelist()}
        required = ("payload/source.json", "payload/main.wasm", "payload/icon.png")
        missing = [name for name in required if name not in names]
        if missing:
            raise ValueError(f"{label} is missing {', '.join(missing)}")
        if archive.getinfo(names["payload/main.wasm"]).file_size == 0:
            raise ValueError(f"{label} contains an empty WebAssembly payload")
        manifest = json.loads(archive.read(names["payload/source.json"]).decode("utf-8-sig"))
        icon = archive.read(names["payload/icon.png"])
    info = manifest.get("info", manifest)
    return info, icon


def load_current(catalog_root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    index_path = catalog_root / "index.min.json"
    inventory_path = catalog_root / "inventory.json"
    if not index_path.exists() or not inventory_path.exists():
        return {}, {}
    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    return (
        {entry["id"]: entry for entry in index.get("sources", [])},
        {entry["id"]: entry for entry in inventory.get("sources", [])},
    )


def load_package(upstream: dict, entry: dict, current_index: dict, current_inventory: dict) -> bytes:
    source_id = str(entry.get("id", ""))
    version = int(entry.get("version", 0))
    old_entry = current_index.get(source_id, {})
    old_inventory = current_inventory.get(source_id, {})
    if (
        int(old_entry.get("version", -1)) == version
        and old_inventory.get("repository") == upstream["name"]
    ):
        old_reference = old_entry.get("downloadURL", "")
        old_path = ROOT / old_reference
        if old_reference and old_path.is_file():
            return old_path.read_bytes()
    return fetch_bytes(package_url(upstream, entry))


def candidate_from_entry(
    upstream: dict,
    entry: dict,
    current_index: dict[str, dict],
    current_inventory: dict[str, dict],
) -> dict:
    package = load_package(upstream, entry, current_index, current_inventory)
    info, icon = read_package(package, f"{upstream['name']}:{entry.get('id')}")

    source_id = str(info.get("id") or entry.get("id") or "")
    name = str(info.get("name") or entry.get("name") or source_id)
    version = int(info.get("version", entry.get("version", 0)))
    languages = [
        str(value)
        for value in as_list(info.get("languages", info.get("lang")))
    ] or entry_languages(entry)
    if not any(language.casefold() in ENGLISH_MARKERS for language in languages):
        raise ValueError(f"{source_id} package no longer advertises English or multilingual support")

    urls = [str(value) for value in as_list(info.get("urls"))]
    if info.get("url"):
        urls.insert(0, str(info["url"]))
    if not urls and entry.get("baseURL"):
        urls.append(str(entry["baseURL"]))

    content_rating = info.get("contentRating", info.get("nsfw"))
    if content_rating is None:
        content_rating = entry.get("contentRating", entry.get("nsfw", 0))
    minimum_app_version = info.get("minAppVersion", entry.get("minAppVersion"))

    return {
        "id": source_id,
        "name": name,
        "version": version,
        "languages": languages,
        "contentRating": int(content_rating),
        "baseURL": urls[0] if urls else str(entry.get("baseURL", "")),
        "minAppVersion": str(minimum_app_version) if minimum_app_version else None,
        "urls": urls,
        "urlKey": normalized_url_key(urls),
        "package": package,
        "icon": icon,
        "repository": upstream["name"],
        "priority": int(upstream["priority"]),
        "license": upstream["license"],
    }


def select_candidates(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    by_id: dict[str, dict] = {}
    for candidate in candidates:
        current = by_id.get(candidate["id"])
        preferred_repository = SOURCE_PREFERENCES.get(candidate["id"])
        rank = (
            candidate["repository"] == preferred_repository,
            candidate["priority"],
            candidate["version"],
        )
        current_rank = (
            current is not None and current["repository"] == preferred_repository,
            current["priority"] if current else -1,
            current["version"] if current else -1,
        )
        if current is None or rank > current_rank:
            by_id[candidate["id"]] = candidate

    selected_by_site: dict[str, dict] = {}
    duplicates: list[dict] = []
    for candidate in sorted(by_id.values(), key=lambda item: item["id"]):
        key = candidate["urlKey"] or f"id:{candidate['id']}"
        current = selected_by_site.get(key)
        if current is None:
            selected_by_site[key] = candidate
            continue
        if (candidate["priority"], candidate["version"]) > (
            current["priority"],
            current["version"],
        ):
            kept, excluded = candidate, current
            selected_by_site[key] = candidate
        else:
            kept, excluded = current, candidate
        duplicates.append(
            {
                "excludedId": excluded["id"],
                "keptId": kept["id"],
                "normalizedSite": key,
            }
        )
    return sorted(selected_by_site.values(), key=lambda item: item["id"]), duplicates


def write_catalog(
    selected: list[dict],
    duplicates: list[dict],
    catalog_root: Path,
    list_name: str,
    inventory_name: str,
    catalog_policy: str,
    catalog_upstreams: tuple[dict, ...],
) -> None:
    if len(selected) < 20:
        raise RuntimeError(f"Safety check stopped an unexpectedly small catalog: {len(selected)}")

    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    catalog_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aidoku-refresh-", dir=catalog_root) as temp_name:
        temp = Path(temp_name)
        source_dir = temp / "sources"
        icon_dir = temp / "icons"
        source_dir.mkdir()
        icon_dir.mkdir()

        index_entries = []
        inventory_entries = []
        checksum_lines = []
        for source in selected:
            package_name = f"{source['id']}-v{source['version']}.aix"
            icon_name = f"{source['id']}-v{source['version']}.png"
            package_path = source_dir / package_name
            icon_path = icon_dir / icon_name
            package_path.write_bytes(source["package"])
            icon_path.write_bytes(source["icon"])
            digest = hashlib.sha256(source["package"]).hexdigest()
            checksum_lines.append(f"{digest}  sources/{package_name}")

            index_entry = {
                "id": source["id"],
                "name": source["name"],
                "version": source["version"],
                "iconURL": f"icons/{icon_name}",
                "downloadURL": f"sources/{package_name}",
                "languages": source["languages"],
                "contentRating": source["contentRating"],
                "baseURL": source["baseURL"],
            }
            if source["minAppVersion"]:
                index_entry["minAppVersion"] = source["minAppVersion"]
            index_entries.append(index_entry)
            inventory_entries.append(
                {
                    "id": source["id"],
                    "name": source["name"],
                    "version": source["version"],
                    "file": f"sources/{package_name}",
                    "repository": source["repository"],
                    "license": source["license"],
                    "sha256": digest,
                }
            )

        source_list = {"name": list_name, "sources": index_entries}
        inventory = {
            "name": inventory_name,
            "generatedAt": checked_at,
            "sourceCount": len(inventory_entries),
            "catalogPolicy": catalog_policy,
            "languagePolicy": "English or multilingual entries advertising en, All, or multi",
            "excludedPersonalUseOnly": ["en.atsumaru", "multi.mangaball", "multi.onisaga"],
            "replacedWithCommunityBuilds": ["multi.mangadotnet", "multi.kagane"],
            "excludedNonEnglish": ["Non-English-only source packages"],
            "upstreams": [
                {"repository": upstream["name"], "index": upstream["index"], "license": upstream["license"]}
                for upstream in catalog_upstreams
            ],
            "excludedDuplicates": duplicates,
            "sources": inventory_entries,
        }

        (temp / "index.min.json").write_text(
            json.dumps(source_list, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        (temp / "index.json").write_text(
            json.dumps(source_list, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        for directory in ("sources", "icons"):
            destination = catalog_root / directory
            destination.mkdir(exist_ok=True)
            for old_item in destination.iterdir():
                if old_item.is_dir():
                    shutil.rmtree(old_item)
                else:
                    old_item.unlink()
            for new_item in (temp / directory).iterdir():
                shutil.copy2(new_item, destination / new_item.name)
        for filename in ("index.min.json", "index.json", "inventory.json", "CHECKSUMS.sha256"):
            shutil.move(str(temp / filename), catalog_root / filename)

    readme_path = catalog_root / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8-sig")
        readme = re.sub(
            r"This repository contains \d+ validated `\.aix` packages\.",
            f"This repository contains {len(selected)} validated `.aix` packages.",
            readme,
        )
        readme_path.write_text(readme, encoding="utf-8")
    (catalog_root / ".nojekyll").touch()


def main() -> None:
    current_index, current_inventory = load_current(ROOT)
    legacy_index, legacy_inventory = load_current(ROOT / "legacy")
    current_index.update(legacy_index)
    current_inventory.update(legacy_inventory)
    candidates: list[dict] = []
    for upstream in UPSTREAMS:
        payload = fetch_json(upstream["index"])
        entries = payload.get("sources", []) if isinstance(payload, dict) else payload
        english_entries = [entry for entry in entries if entry and is_english_entry(entry)]
        print(f"{upstream['name']}: {len(english_entries)} English/multilingual index entries")
        for entry in english_entries:
            candidates.append(candidate_from_entry(upstream, entry, current_index, current_inventory))

    active_candidates = [
        candidate for candidate in candidates if candidate["repository"] == ACTIVE_REPOSITORY
    ]
    active_selected, active_duplicates = select_candidates(active_candidates)
    all_selected, all_duplicates = select_candidates(candidates)

    active_upstreams = tuple(
        upstream for upstream in UPSTREAMS if upstream["name"] == ACTIVE_REPOSITORY
    )
    write_catalog(
        active_selected,
        active_duplicates,
        ROOT,
        "Nixzle's Maintained English Aidoku Sources",
        "Nixzle's Maintained Public English Aidoku Sources",
        "Packages currently published by the active Aidoku community repository",
        active_upstreams,
    )
    write_catalog(
        all_selected,
        all_duplicates,
        ROOT / "legacy",
        "Nixzle's Legacy English Aidoku Sources",
        "Nixzle's Legacy Public English Aidoku Sources",
        "Active packages plus older, unmaintained packages that may no longer work",
        UPSTREAMS,
    )
    print(
        f"Published {len(active_selected)} maintained sources and "
        f"{len(all_selected)} sources in the legacy catalog"
    )


if __name__ == "__main__":
    main()

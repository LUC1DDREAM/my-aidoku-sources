from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.validate_catalog import ValidationFailure, safe_relative_path, validate_aix


class ValidateCatalogTests(unittest.TestCase):
    def test_safe_relative_path_accepts_catalog_asset(self) -> None:
        path = safe_relative_path("sources/en.example-v1.aix", "downloadURL", "sources")
        self.assertEqual(path.as_posix(), "sources/en.example-v1.aix")

    def test_safe_relative_path_rejects_parent_traversal(self) -> None:
        with self.assertRaises(ValidationFailure):
            safe_relative_path("sources/../index.json", "downloadURL", "sources")

    def test_validate_aix_checks_manifest_and_payload_headers(self) -> None:
        entry = {"id": "en.example", "version": 1}
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = Path(temporary_directory) / "en.example-v1.aix"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "Payload/source.json",
                    json.dumps({"info": {"id": "en.example", "version": 1}}),
                )
                archive.writestr("Payload/icon.png", b"\x89PNG\r\n\x1a\nfixture")
                archive.writestr("Payload/main.wasm", b"\x00asmfixture")

            digest = validate_aix(package, entry, "test catalog")
            self.assertEqual(len(digest), 64)

    def test_validate_aix_rejects_manifest_version_mismatch(self) -> None:
        entry = {"id": "en.example", "version": 2}
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = Path(temporary_directory) / "en.example-v2.aix"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "Payload/source.json",
                    json.dumps({"info": {"id": "en.example", "version": 1}}),
                )
                archive.writestr("Payload/icon.png", b"\x89PNG\r\n\x1a\nfixture")
                archive.writestr("Payload/main.wasm", b"\x00asmfixture")

            with self.assertRaises(ValidationFailure):
                validate_aix(package, entry, "test catalog")


if __name__ == "__main__":
    unittest.main()

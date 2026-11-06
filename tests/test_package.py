"""Offline packaging tests; do not import Home Assistant or integration code."""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts import build_release

SOURCE_ROOT = Path(__file__).resolve().parent.parent


class PackageTests(unittest.TestCase):
    """Exercise packaging in an isolated repository without network or device I/O."""

    def setUp(self) -> None:
        """Copy only public repository inputs into a disposable local Git index."""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.integration = self.root / "custom_components" / "smarwi"
        shutil.copytree(SOURCE_ROOT / "custom_components" / "smarwi", self.integration)
        shutil.copyfile(SOURCE_ROOT / "LICENSE", self.root / "LICENSE")
        shutil.copyfile(SOURCE_ROOT / "hacs.json", self.root / "hacs.json")
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.git_add("custom_components/smarwi")
        self.output = self.root / "dist" / "smarwi.zip"
        self.manifest_path = self.integration / "manifest.json"
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.tag = self.manifest["version"]
        self.addCleanup(patch.stopall)
        patch.object(build_release, "ROOT", self.root).start()

    def git_add(self, path: str) -> None:
        """Stage a fixture without creating commits or configuring a Git identity."""
        subprocess.run(["git", "-C", str(self.root), "add", "--", path], check=True)

    def test_flat_archive_preserves_sources_and_license(self) -> None:
        """Ship exactly the integration contents and unchanged root license."""
        expected = {
            path.relative_to(self.integration).as_posix(): path.read_bytes()
            for path in self.integration.rglob("*") if path.is_file()
        }
        expected["LICENSE"] = (self.root / "LICENSE").read_bytes()
        build_release.build_release(self.output, self.tag)
        with ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), set(expected))
            for name, content in expected.items():
                self.assertEqual(archive.read(name), content)
                self.assertEqual(Path(name).is_absolute(), False)
                self.assertNotIn("..", Path(name).parts)
            self.assertEqual(json.loads(archive.read("manifest.json"))["version"], self.tag)
        for name, content in expected.items():
            source = self.root / "LICENSE" if name == "LICENSE" else self.integration / name
            self.assertEqual(source.read_bytes(), content)

    def test_untracked_and_workspace_files_are_excluded(self) -> None:
        """Do not include local configuration, parent handoffs, caches, or outputs."""
        for name in (
            "secrets.yaml", ".git/config.local", ".pi/settings.json", ".handoffs/PLAN.md",
            "config/configuration.yaml", "dist/previous.zip",
            "custom_components/smarwi/local_config.json",
            "custom_components/smarwi/__pycache__/device.pyc",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("excluded fixture", encoding="utf-8")
        build_release.build_release(self.output, self.tag)
        with ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertNotIn("local_config.json", names)
            excluded_roots = {".git", ".pi", ".handoffs", "config", "dist", "__pycache__"}
            self.assertFalse(any(Path(name).parts[0] in excluded_roots for name in names))

    def test_tag_must_match_manifest_exactly(self) -> None:
        """Reject mismatches and implicit v-prefix normalization before writing."""
        for tag in ("", f"v{self.tag}", "9.9.9"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "exactly match"):
                build_release.build_release(self.output, tag)
        self.assertFalse(self.output.exists())

    def test_invalid_metadata_is_rejected(self) -> None:
        """Reject malformed JSON and missing or changed integration identity."""
        for data in ("{", "[]", "{}", json.dumps({**self.manifest, "domain": "renamed"})):
            with self.subTest(data=data):
                self.manifest_path.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_hacs_filename_and_zip_mode_must_agree(self) -> None:
        """Reject an asset name or install mode that does not match HACS metadata."""
        for metadata in ({"zip_release": True, "filename": "wrong.zip"}, {"zip_release": False, "filename": "smarwi.zip"}):
            with self.subTest(metadata=metadata):
                (self.root / "hacs.json").write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "HACS ZIP"):
                    build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_missing_required_file_is_rejected(self) -> None:
        """Do not build an archive without required English UI assets."""
        subprocess.run(["git", "-C", str(self.root), "rm", "--quiet", "--force", "custom_components/smarwi/translations/en.json"], check=True)
        with self.assertRaisesRegex(ValueError, "Missing required"):
            build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_unexpected_tracked_file_is_rejected(self) -> None:
        """Fail if local settings were accidentally staged inside the integration."""
        (self.integration / "secrets.yaml").write_text("excluded fixture", encoding="utf-8")
        self.git_add("custom_components/smarwi/secrets.yaml")
        with self.assertRaisesRegex(ValueError, "Unexpected integration file"):
            build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_symlink_is_rejected(self) -> None:
        """Never follow a tracked integration symlink into files outside its scope."""
        (self.integration / "outside.py").symlink_to(self.root / "LICENSE")
        self.git_add("custom_components/smarwi/outside.py")
        with self.assertRaisesRegex(ValueError, "Unexpected integration file"):
            build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_license_is_required(self) -> None:
        """Do not distribute an integration archive without the license notice."""
        (self.root / "LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "LICENSE"):
            build_release.build_release(self.output, self.tag)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self) -> None:
        """Leave an existing output file intact on a repeated or mistaken build."""
        self.output.parent.mkdir()
        self.output.write_bytes(b"existing output")
        with self.assertRaises(FileExistsError):
            build_release.build_release(self.output, self.tag)
        self.assertEqual(self.output.read_bytes(), b"existing output")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Build a flat HACS ZIP from tracked integration files without changing sources."""

import argparse
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent


def build_release(output: Path, tag: str) -> Path:
    """Validate release metadata and build a new archive without overwriting files."""
    integration = ROOT / "custom_components" / "smarwi"
    try:
        manifest = json.loads(
            (integration / "manifest.json").read_text(encoding="utf-8")
        )
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ValueError(f"Cannot read release metadata: {err}") from err
    if not isinstance(manifest, dict) or not isinstance(hacs, dict):
        raise TypeError("manifest.json and hacs.json must contain JSON objects")
    if manifest.get("domain") != "smarwi":
        raise ValueError("The integration domain must remain smarwi")
    if not tag or manifest.get("version") != tag:
        raise ValueError(
            "The tag must exactly match manifest.json version; no v prefix is added or removed"
        )
    if hacs.get("zip_release") is not True or hacs.get("filename") != output.name:
        raise ValueError("The output filename must match the HACS ZIP release filename")

    tracked = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "-z",
                "--",
                "custom_components/smarwi/",
            ]
        )
        .decode("utf-8")
        .split("\0")
    )
    members = {}
    for name in filter(None, tracked):
        source = ROOT / name
        relative = source.relative_to(integration)
        parts = relative.parts
        allowed = (
            len(parts) == 1
            and (relative.suffix == ".py" or relative.name == "manifest.json")
        ) or (
            len(parts) == 2
            and (
                (parts[0] == "translations" and relative.suffix == ".json")
                or (parts[0] == "brand" and relative.suffix == ".png")
            )
        )
        # Fail on unexpected tracked files rather than silently shipping local data.
        if not allowed or source.is_symlink() or not source.is_file():
            raise ValueError(f"Unexpected integration file: {relative}")
        members[relative.as_posix()] = source

    required = {
        "__init__.py",
        "manifest.json",
        "translations/en.json",
        "brand/icon.png",
    }
    if missing := required - members.keys():
        raise ValueError(f"Missing required integration files: {sorted(missing)}")
    license_path = ROOT / "LICENSE"
    if license_path.is_symlink() or not license_path.is_file():
        raise ValueError("A regular root LICENSE file is required")
    members["LICENSE"] = license_path
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name, source in sorted(members.items()):
            archive.write(source, name)
    return output


def main() -> None:
    """Build a release candidate; this command never uploads or publishes it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        required=True,
        help="Exact manifest version, including any development suffix",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "smarwi.zip")
    args = parser.parse_args()
    try:
        build_release(args.output, args.tag)
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()

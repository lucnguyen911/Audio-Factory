"""Generate verified Supabase metadata for a full installer release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from version import APP_ID, APP_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("installer", type=Path)
    parser.add_argument("google_drive_url")
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--enforcement", choices=("optional", "forced"), default="optional")
    parser.add_argument("--changelog", default="")
    parser.add_argument("--output", type=Path, default=Path("release_metadata.json"))
    args = parser.parse_args()

    if not args.installer.is_file():
        parser.error("installer does not exist")
    with open(args.installer, "rb") as stream:
        if stream.read(2) != b"MZ":
            parser.error("installer is not a Windows executable")
        stream.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    metadata = {
        "app_id": APP_ID,
        "latest_version": args.version,
        "changelog": args.changelog,
        "download_url": args.google_drive_url,
        "sha256": digest.hexdigest(),
        "file_size": args.installer.stat().st_size,
        "package_type": "installer",
        "enforcement": args.enforcement,
        "is_active": True,
    }
    args.output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


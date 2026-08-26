#!/usr/bin/env python3
"""Semantic version helpers for CI and release automation."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
MANIFEST = Path("custom_components/facebox/manifest.json")


def read_manifest() -> dict[str, object]:
    """Read the integration manifest."""
    return json.loads(MANIFEST.read_text())


def semantic_tags() -> list[tuple[tuple[int, int, int], str]]:
    """Return semantic Git tags."""
    parsed = []
    for tag in subprocess.check_output(["git", "tag", "--list"], text=True).splitlines():
        match = TAG_RE.fullmatch(tag.strip())
        if match:
            parsed.append(
                (
                    tuple(int(match.group(part)) for part in ("major", "minor", "patch")),
                    tag,
                )
            )
    return parsed


def manifest_version() -> tuple[int, int, int]:
    """Return the manifest version as a semantic tuple."""
    value = str(read_manifest().get("version", "0.0.0"))
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SystemExit(f"Invalid manifest semantic version: {value!r}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def highest() -> tuple[tuple[int, int, int], str]:
    """Return the highest released tag, falling back to manifest for bootstrap."""
    tags = semantic_tags()
    if tags:
        return max(tags, key=lambda item: item[0])
    version = manifest_version()
    return version, f"v{version_text(version)} (manifest bootstrap)"


def version_text(version: tuple[int, int, int]) -> str:
    """Render a semantic version tuple."""
    return ".".join(map(str, version))


def next_patch() -> tuple[int, int, int]:
    """Return the next patch version."""
    version, _ = highest()
    return version[0], version[1], version[2] + 1


def sync_manifest(version: tuple[int, int, int]) -> bool:
    """Synchronize manifest version and report whether it changed."""
    data = read_manifest()
    expected = version_text(version)
    if data.get("version") == expected:
        return False
    data["version"] = expected
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")
    return True


def main() -> None:
    """Run a version helper command."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "highest",
        "next",
        "check-manifest-current",
        "sync-manifest-current",
        "sync-manifest-next",
    ):
        subparsers.add_parser(command)
    args = parser.parse_args()

    current, current_tag = highest()
    current_text = version_text(current)
    upcoming = next_patch()
    upcoming_text = version_text(upcoming)

    if args.command == "highest":
        print(current_text)
    elif args.command == "next":
        print(upcoming_text)
    elif args.command == "check-manifest-current":
        manifest = str(read_manifest().get("version", ""))
        if manifest != current_text:
            raise SystemExit(
                f"manifest.json version {manifest!r} is out of sync: "
                f"highest semantic Git tag is {current_tag} ({current_text})"
            )
        print(f"Version sync OK: {current_tag}; manifest={manifest}")
    elif args.command == "sync-manifest-current":
        sync_manifest(current)
        print(current_text)
    elif args.command == "sync-manifest-next":
        sync_manifest(upcoming)
        print(upcoming_text)


if __name__ == "__main__":
    main()

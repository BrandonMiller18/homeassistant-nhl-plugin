"""Set the integration version in manifest.json and const.py.

python scripts/bump_version.py 0.3.0      # or 0.3.0b1 for a pre-release
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "nhl_companion"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?$")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("version", help="e.g. 0.3.0 or 0.3.0b1")
    version = parser.parse_args().version.removeprefix("v")
    if not VERSION_RE.match(version):
        parser.error(f"{version!r} is not X.Y.Z or X.Y.Z(a|b|rc)N")

    manifest_path = COMPONENT / "manifest.json"
    old = json.loads(manifest_path.read_text())["version"]
    # Edit the text rather than re-dumping the JSON, so formatting is untouched
    _replace(manifest_path, r'^(\s*"version": )".*"', rf'\g<1>"{version}"')
    _replace(COMPONENT / "const.py", r'^VERSION: Final = ".*"$', f'VERSION: Final = "{version}"')
    print(f"{old} -> {version}")


def _replace(path: Path, pattern: str, repl: str) -> None:
    text, count = re.subn(pattern, repl, path.read_text(), count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"version not found in {path.name}")
    path.write_text(text)


if __name__ == "__main__":
    main()

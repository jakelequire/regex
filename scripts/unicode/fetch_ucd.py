"""Download the Unicode Character Database files the table generator reads.

Usage: python scripts/unicode/fetch_ucd.py <destination-directory>

The version is pinned here and in generate_tables.py; both must change
together when the library moves to a new Unicode release.
"""

import pathlib
import sys
import urllib.request

UNICODE_VERSION = "17.0.0"

FILES = [
    "UnicodeData.txt",
    "PropList.txt",
    "DerivedCoreProperties.txt",
    "Scripts.txt",
    "ScriptExtensions.txt",
    "PropertyAliases.txt",
    "PropertyValueAliases.txt",
    "CaseFolding.txt",
    "emoji/emoji-data.txt",
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    destination = pathlib.Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    base = f"https://www.unicode.org/Public/{UNICODE_VERSION}/ucd/"
    for name in FILES:
        target = destination / pathlib.PurePosixPath(name).name
        print(f"fetching {name}")
        with urllib.request.urlopen(base + name) as response:
            target.write_bytes(response.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())

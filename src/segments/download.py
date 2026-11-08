"""Download the two Online Retail II files from a pinned commit and verify checksums."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "data" / "sources.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(raw_dir: Path, sources: Path = SOURCES) -> list[Path]:
    spec = json.loads(sources.read_text())
    base = spec["mirror"].replace("github.com", "raw.githubusercontent.com")
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name, meta in spec["files"].items():
        dest = raw_dir / name
        if not dest.exists() or sha256(dest) != meta["sha256"]:
            url = f"{base}/{spec['mirror_commit']}/{spec['mirror_path']}/{name}"
            print(f"downloading {name} ({meta['bytes'] / 1e6:.0f} MB)")
            urllib.request.urlretrieve(url, dest)
        got = sha256(dest)
        if got != meta["sha256"]:
            raise ValueError(f"{name}: checksum {got} does not match {meta['sha256']}")
        out.append(dest)
    return out


if __name__ == "__main__":
    for p in fetch(ROOT / "data" / "raw"):
        print("verified", p.name)

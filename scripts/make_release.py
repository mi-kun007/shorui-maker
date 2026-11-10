#!/usr/bin/env python3
"""配布物を作る。git の中身だけを zip にして、SHA256 入りの manifest を添える。

    python3 scripts/make_release.py [出力先フォルダ]

出来る物: dist/paper-maker-vX.Y.Z.zip と dist/manifest.json
この2つを GitHub Releases に上げると `paper-maker update` が拾う。
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE_URL = "https://github.com/mi-kun007/shorui-maker/releases/latest/download"


def main():
    out = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT / "dist"
    out.mkdir(parents=True, exist_ok=True)
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    zip_path = out / ("paper-maker-v%s.zip" % ver)

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print("注意: コミットしていない変更があります。zip には入りません:\n" + dirty)

    subprocess.run(["git", "archive", "--format=zip", "-o", str(zip_path),
                    "--prefix=paper-maker/", "HEAD"], cwd=ROOT, check=True)
    data = zip_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    manifest = {"version": ver, "zip": "%s/%s" % (BASE_URL, zip_path.name), "sha256": digest}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("zip     :", zip_path, "(%.1f KB)" % (len(data) / 1024))
    print("sha256  :", digest)
    print("manifest:", out / "manifest.json")
    print("\nGitHub Releases に上げる:")
    print("  gh release create v%s %s %s -R mi-kun007/shorui-maker" % (ver, zip_path, out / "manifest.json"))


if __name__ == "__main__":
    main()

"""Build distributable release assets from a clean, reviewed source tree."""

import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from general_agent_os import __version__  # noqa: E402

subprocess.run([sys.executable, "-m", "build"], cwd=ROOT, check=True)
dist = ROOT / "dist"
archive = dist / f"GeneralAgentOS-{__version__}.zip"
allowed_files = ["pyproject.toml", "README.md", "README.zh-CN.md", "LICENSE", "CHANGELOG.md",
                 "install.sh", "Dockerfile", "compose.yaml", ".env.example", ".gitignore", ".dockerignore"]
paths = [ROOT / file for file in allowed_files]
for folder in ("src", "tests", "examples", "docs", "scripts", ".github"):
    paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                 and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".db", ".log"})
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
    for file in sorted(paths):
        out.write(file, f"GeneralAgentOS-{__version__}/" + str(file.relative_to(ROOT)))
assets = [archive, dist / f"general_agent_os-{__version__}-py3-none-any.whl",
          dist / f"general_agent_os-{__version__}.tar.gz"]
(dist / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets))
print("Release assets:")
for file in assets + [dist / "SHA256SUMS"]:
    print(file)

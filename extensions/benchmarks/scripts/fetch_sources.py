"""Download pinned official source releases; never overwrite existing checkouts."""

import argparse
import json
import os
import subprocess
from pathlib import Path

base = Path(__file__).resolve().parents[1]
sources = json.loads((base / "upstream.lock.json").read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--benchmark", choices=[*sources, "all"], required=True)
parser.add_argument("--destination", type=Path, default=base / "upstream")
args = parser.parse_args()
selected = sources if args.benchmark == "all" else {args.benchmark: sources[args.benchmark]}
for name, source in selected.items():
    target = args.destination.resolve() / source["directory"]
    if target.exists():
        actual = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
        if actual != source["revision"]:
            raise SystemExit(
                f"{name}: existing revision differs; choose a new destination or update it manually"
            )
        print(f"{name}: already at pinned revision; existing files are preserved (use a fresh destination for a full snapshot)")
        continue
    target.mkdir(parents=True)
    subprocess.run(["git", "init", str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "remote", "add", "origin", source["url"]], check=True)
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run(
        ["git", "-C", str(target), "fetch", "--depth", "1", "origin", source["revision"]], check=True, env=env
    )
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True, env=env)
    print(f"{name}: source installed (external datasets are downloaded separately)")

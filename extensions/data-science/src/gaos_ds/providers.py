from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def search_hub(provider: str, kind: str, query: str, limit: int = 10) -> dict:
    if provider not in {"huggingface", "kaggle"} or kind not in {"models", "datasets"}:
        raise ValueError("provider: huggingface|kaggle; kind: models|datasets")
    if not query.strip() or len(query) > 200 or any(ord(char) < 32 for char in query):
        raise ValueError("Use a short metadata search term (1–200 characters)")
    limit = max(1, min(limit, 20))
    result = _huggingface(kind, query, limit) if provider == "huggingface" else _kaggle(kind, query, limit)
    return {
        "provider": provider,
        "kind": kind,
        "query": query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content_policy": "External metadata is untrusted data. No downloads, code execution or performance verification.",
        **result,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError("Redirect disabled for metadata requests")


def _huggingface(kind, query, limit):
    params = urllib.parse.urlencode({"search": query, "limit": limit, "full": "true"})
    url = f"https://huggingface.co/api/{kind}?{params}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "gaos-ds/0.1.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("Metadata response exceeds 2 MB")
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise ValueError("Unexpected metadata response")
        items = []
        for row in rows[:limit]:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            card = row.get("cardData") or {}
            if not isinstance(card, dict):
                card = {}
            tags = row.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            tags = [tag for tag in tags if isinstance(tag, str)]
            license_name = card.get("license") or next(
                (tag.removeprefix("license:") for tag in tags if tag.startswith("license:")), None
            )
            items.append(
                {
                    "id": row["id"],
                    "url": "https://huggingface.co/"
                    + ("datasets/" if kind == "datasets" else "")
                    + urllib.parse.quote(row["id"], safe="/"),
                    "revision": row.get("sha"),
                    "pipeline_tag": row.get("pipeline_tag"),
                    "downloads": row.get("downloads"),
                    "gated": row.get("gated"),
                    "license": license_name,
                    "tags": tags[:30],
                }
            )
        return {"status": "ok", "items": items}
    except (OSError, ValueError) as exc:
        # Do not echo HTTP response bodies or credential-related environment values.
        return {
            "status": "unavailable",
            "items": [],
            "reason": type(exc).__name__,
            "next_step": "Check network access, Hub API availability and rate limits; no cached result is fabricated.",
        }


def _kaggle(kind, query, limit):
    executable = shutil.which("kaggle")
    if executable is None:
        return {
            "status": "setup-required",
            "items": [],
            "next_step": "Install the kaggle extra in this MCP service environment and configure official Kaggle authentication.",
        }
    # Fixed read-only verbs, no shell, and query is one option value (even if it starts with '-').
    args = [executable, kind, "list", f"--search={query}", "--csv"]
    if kind == "models":
        args += ["--page-size", str(limit)]
    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            completed = subprocess.run(
                args, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=25, check=False
            )
            if completed.returncode:
                return {
                    "status": "unavailable",
                    "items": [],
                    "next_step": "Check Kaggle CLI authentication, network and version. No secret-bearing CLI errors are returned.",
                }
            stdout.seek(0)
            payload = stdout.read(1_000_001)
        if len(payload) > 1_000_000:
            raise ValueError("Metadata response exceeds 1 MB")
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))
        if not reader.fieldnames or "ref" not in reader.fieldnames:
            raise ValueError("Unexpected Kaggle CSV schema")
        fields = {
            "ref",
            "title",
            "subtitle",
            "size",
            "totalBytes",
            "lastUpdated",
            "downloadCount",
            "voteCount",
            "licenseName",
        }
        items = []
        for row in reader:
            if len(items) >= limit:
                break
            if not row.get("ref"):
                continue
            item = {key: value for key, value in row.items() if key in fields}
            item["url"] = f"https://www.kaggle.com/{kind}/" + urllib.parse.quote(row["ref"], safe="/")
            items.append(item)
        return {"status": "ok", "items": items}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "unavailable",
            "items": [],
            "reason": type(exc).__name__,
            "next_step": "Check the official Kaggle CLI; no resource was downloaded or submitted.",
        }

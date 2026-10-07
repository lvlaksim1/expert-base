from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "expert-templates" / ".context" / "expert"
VERSION = (ROOT / "EXPERT_BASE_VERSION").read_text(encoding="utf-8").strip()
PROVENANCE = json.loads((ROOT / "SOURCE_PROVENANCE.json").read_text(encoding="utf-8"))
LOCK_PATH = TEMPLATE_ROOT / "training" / "TRAINING_BASELINE.lock.json"
ENTRYPOINT_MARKER = "<!-- EXPERT-BASE-OVERLAY -->"


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def fetch_blob(repository: str, sha: str) -> bytes:
    url = f"https://api.github.com/repos/{repository}/git/blobs/{sha}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "expert-base-installer"})
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = base64.b64decode(payload["content"].replace("\n", ""))
    actual = git_blob_sha(data)
    if actual != sha:
        raise RuntimeError(f"blob verification failed: expected {sha}, got {actual}")
    return data


def copy_overlay(target: Path, expert_id: str, specialization: str, force: bool) -> None:
    service_contract = target / ".context" / "service-agent" / "CONTRACT.md"
    if not service_contract.exists():
        raise RuntimeError(
            "service-agent-base is required first; missing .context/service-agent/CONTRACT.md"
        )

    destination = target / ".context" / "expert"
    if destination.exists() and any(destination.iterdir()) and not force:
        raise RuntimeError(".context/expert already exists; use --force only for an intentional overlay refresh")

    shutil.copytree(TEMPLATE_ROOT, destination, dirs_exist_ok=True)
    replacements = {
        "{{EXPERT_ID}}": expert_id,
        "{{SPECIALIZATION}}": specialization,
        "{{EXPERT_BASE_VERSION}}": VERSION,
    }
    for path in destination.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    identity = {
        "schema": "expert-identity-v1",
        "expert_id": expert_id,
        "specialization": specialization,
        "expert_base_version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "service_agent_base": PROVENANCE["service_agent_base"],
        "expert_training": PROVENANCE["expert_training"],
        "identity_rule": "separate-from-project-managers-and-runtime",
    }
    (destination / "identity.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    entrypoint = target / ".context" / "ENTRYPOINT.md"
    text = entrypoint.read_text(encoding="utf-8") if entrypoint.exists() else "# Context Entrypoint\n"
    if ENTRYPOINT_MARKER not in text:
        text += (
            "\n" + ENTRYPOINT_MARKER + "\n"
            "## Expert overlay\n"
            "After the mandatory service-agent context, read `.context/expert/ENTRYPOINT.md`.\n"
        )
        entrypoint.write_text(text, encoding="utf-8")


def sync_training(target: Path) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    repository = lock["source_repository"]
    out = target / ".context" / "expert" / "training" / "specs"
    out.mkdir(parents=True, exist_ok=True)
    entries = list(lock["source_files"].items())
    for index, (name, sha) in enumerate(entries):
        if index:
            time.sleep(5.0)
        data = fetch_blob(repository, sha)
        (out / name).write_bytes(data)


def apply(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        raise RuntimeError(f"target does not exist: {target}")
    copy_overlay(target, args.expert_id, args.specialization, args.force)
    if not args.no_sync_training:
        sync_training(target)
    print(f"Expert overlay {VERSION} applied to {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Expert Base overlay to a Service Agent repository")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--target", required=True)
    p.add_argument("--expert-id", required=True)
    p.add_argument("--specialization", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-sync-training", action="store_true")
    p.set_defaults(func=apply)
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

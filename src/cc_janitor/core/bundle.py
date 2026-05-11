from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .safety import require_confirmed
from .state import get_paths

FileKind = Literal["claude_md", "skill", "settings", "memory", "mcp_config"]

# Hard-exclude these — settings.local.json holds local secrets / permission
# allowlist, .env / credentials.json / .secret / *_token are obvious.
SECRET_PATTERNS = [
    re.compile(r"settings\.local\.json$"),
    re.compile(r"\.env$"),
    re.compile(r"credentials\.json$"),
    re.compile(r"\.secret$"),
    re.compile(r"_token$"),
]


@dataclass
class BundleEntry:
    src_path: Path
    arcname: str
    kind: FileKind


def _is_secret(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in SECRET_PATTERNS)


def _iter_sources(*, include_memory: bool) -> Iterator[BundleEntry]:
    # get_paths().home is ~/.cc-janitor; its parent is $HOME.
    home = get_paths().home.parent
    cwd = Path.cwd()

    # ~/.claude/CLAUDE.md
    p = home / ".claude" / "CLAUDE.md"
    if p.exists() and not _is_secret(p):
        yield BundleEntry(p, "claude/CLAUDE.md", "claude_md")

    # ~/.claude/skills/**
    skills_root = home / ".claude" / "skills"
    if skills_root.is_dir():
        for f in sorted(skills_root.rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            if _is_secret(f):
                continue
            rel = f.relative_to(home / ".claude")
            yield BundleEntry(f, f"claude/{rel.as_posix()}", "skill")

    # ~/.claude/settings.json (NOT settings.local.json)
    p = home / ".claude" / "settings.json"
    if p.exists() and not _is_secret(p):
        yield BundleEntry(p, "claude/settings.json", "settings")

    # cwd/.claude/settings.json (NOT local)
    p = cwd / ".claude" / "settings.json"
    if p.exists() and not _is_secret(p):
        yield BundleEntry(p, "project/settings.json", "settings")

    if include_memory:
        proj_root = home / ".claude" / "projects"
        if proj_root.is_dir():
            for proj in sorted(proj_root.iterdir()):
                mem = proj / "memory"
                if not mem.is_dir():
                    continue
                for f in sorted(mem.rglob("*.md")):
                    if ".archive" in f.parts:
                        continue
                    if _is_secret(f):
                        continue
                    rel = f.relative_to(home / ".claude")
                    yield BundleEntry(f, f"claude/{rel.as_posix()}", "memory")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_bundle(out_path: Path, *, include_memory: bool = False) -> int:
    """Write a tar.gz bundle of safe-to-share Claude config files.

    Hard-excludes ``settings.local.json`` and other secret-file patterns
    (no opt-out flag). ``manifest.json`` is the first member of the tar
    for fast inspection without full extract.
    """
    entries = list(_iter_sources(include_memory=include_memory))
    files_meta: list[dict] = []
    cached: dict[str, bytes] = {}
    for e in entries:
        data = e.src_path.read_bytes()
        cached[e.arcname] = data
        files_meta.append({
            "path": str(e.src_path),
            "arcname": e.arcname,
            "sha256": _sha256(data),
            "kind": e.kind,
            "size": len(data),
        })
    manifest = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "cc_janitor_version": "0.3.0.dev0",
        "files": files_meta,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest_bytes)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for arcname, data in cached.items():
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return len(entries)


def _verify_member(tar: tarfile.TarFile, arcname: str, expected_sha: str) -> bytes:
    member = tar.extractfile(arcname)
    if member is None:
        raise ValueError(f"Bundle missing member: {arcname}")
    data = member.read()
    actual = _sha256(data)
    if actual != expected_sha:
        raise ValueError(
            f"SHA mismatch for {arcname}: expected {expected_sha}, got {actual}"
        )
    return data


def _resolve_dest(arcname: str) -> Path | None:
    """Return the destination path on disk, or None for non-file entries."""
    home = get_paths().home.parent
    cwd = Path.cwd()
    if arcname == "manifest.json":
        return None
    if arcname.startswith("claude/"):
        return home / ".claude" / arcname[len("claude/"):]
    if arcname.startswith("project/"):
        return cwd / ".claude" / arcname[len("project/"):]
    raise ValueError(f"Unknown bundle arcname prefix: {arcname}")


def import_bundle(
    bundle_path: Path, *, dry_run: bool, force: bool
) -> dict:
    """Import a bundle into the local Claude config tree.

    - Requires CC_JANITOR_USER_CONFIRMED=1.
    - Verifies SHA-256 of every member against the manifest before writing.
    - Backs up existing destination files to
      ``~/.cc-janitor/backups/import-<ts>/`` before overwrite.
    - Writes atomically via ``os.replace``.
    """
    require_confirmed()
    backups: list[Path] = []
    written: list[Path] = []
    plan_writes = 0

    with tarfile.open(bundle_path, "r:gz") as tar:
        mf = tar.extractfile("manifest.json")
        if mf is None:
            raise ValueError("Bundle has no manifest.json")
        manifest = json.loads(mf.read().decode("utf-8"))
        if manifest.get("version") != 1:
            raise ValueError(
                f"Unsupported bundle version: {manifest.get('version')}"
            )
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_root = get_paths().backups / f"import-{ts}"

        for entry in manifest["files"]:
            arcname = entry["arcname"]
            data = _verify_member(tar, arcname, entry["sha256"])
            dest = _resolve_dest(arcname)
            if dest is None:
                continue
            if dest.exists():
                existing = dest.read_bytes()
                if _sha256(existing) == entry["sha256"]:
                    continue  # already identical
            plan_writes += 1
            if dry_run or not force:
                continue
            if dest.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                bp = backup_root / dest.name
                # Avoid clobbering if two members share a basename.
                if bp.exists():
                    bp = backup_root / f"{dest.name}.{len(backups)}"
                shutil.copy2(dest, bp)
                backups.append(bp)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".cc-janitor-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            written.append(dest)

    return {
        "would_write": plan_writes,
        "written": len(written),
        "backups": [str(b) for b in backups],
        "destinations": [str(d) for d in written],
    }

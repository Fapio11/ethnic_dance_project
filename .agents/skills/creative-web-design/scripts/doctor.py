#!/usr/bin/env python3
"""Read-only, bounded dependency discovery. Standard library; Python 3.9+.

No downloads, credentials, upstream status/configuration scripts, activation,
package imports, or installation are performed. --media probes only selected
Python/ffmpeg/ffprobe executables with fixed version arguments and inspects
Pillow distribution metadata. This is dependency evidence, not pipeline QA.
Exit: 0 required dependencies available; 2 missing/ambiguous; 1 input/read error.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from skill_utils import MAX_ENTRY_BYTES, parse_frontmatter, read_frontmatter

EXPECTED = {"taste": "design-taste-frontend", "impeccable": "impeccable", "oil-motion": "oil-motion"}
ALIASES = {"design-taste-frontend": "taste", "oil_motion": "oil-motion"}
EXCLUDED = {"node_modules", ".venv", "venv", ".git", "__pycache__", ".cache", "cache", "caches"}
MAX_CHILDREN = 512
MAX_ANCESTORS = 64


def issue(code, message, path=None):
    result = {"code": code, "message": message}
    if path is not None:
        result["path"] = str(path)
    return result


def read_issue(code, exc, path):
    # Exception strings can embed private paths; retain type/errno instead.
    return issue(code, "%s (errno=%s)" % (type(exc).__name__, getattr(exc, "errno", None)), path)


def _resolved(path):
    return Path(path).expanduser().resolve()


def search_roots(project, extra, environment=None, home=None):
    """Return fixed known locations, bounded ancestor locations, and explicit roots."""
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else Path(home)
    roots, seen = [], set()

    def add(path, origin, explicit=False):
        resolved = _resolved(path)
        if resolved not in seen:
            seen.add(resolved)
            roots.append({"path": str(resolved), "origin": origin, "explicit": explicit})

    current = _resolved(project)
    for _ in range(MAX_ANCESTORS):
        add(current / ".agents" / "skills", "project-ancestor")
        if (current / ".git").exists() or current.parent == current:
            break
        current = current.parent
    else:
        raise ValueError("Project ancestor depth exceeds the discovery bound")
    add(home / ".agents" / "skills", "user-agents")
    codex_home = environment.get("CODEX_HOME")
    if codex_home:
        add(Path(codex_home) / "skills", "codex-home")
    else:
        add(home / ".codex" / "skills", "user-codex-fallback")
    for path in extra:
        add(path, "explicit", True)
    return roots


def entry_paths(root_record):
    """Scan only a root and its immediate skill directories; never recursive."""
    root = Path(root_record["path"])
    root_record["entries_scanned"] = 0
    if not root.exists():
        root_record["status"] = "missing"
        return [], ([issue("invalid-root", "Explicit Skill root does not exist", root)] if root_record["explicit"] else [])
    if not root.is_dir():
        root_record["status"] = "invalid"
        return [], [issue("invalid-root", "Skill root must be a directory", root)]
    try:
        direct = root / "SKILL.md"
        if direct.is_file():
            root_record["status"], root_record["entries_scanned"] = "scanned", 1
            return [direct], []
        children = []
        # Bound directory enumeration before sorting, even on a large extra root.
        with os.scandir(root) as listing:
            for index, item in enumerate(listing):
                if index >= MAX_CHILDREN:
                    root_record["status"] = "bounded-error"
                    return [], [issue("scan-bound", "Skill root exceeds %d immediate entries" % MAX_CHILDREN, root)]
                if item.name in EXCLUDED or item.name.startswith("."):
                    continue
                if item.is_dir(follow_symlinks=True):
                    children.append(Path(item.path))
        entries = []
        for child in sorted(children):
            entry = child / "SKILL.md"
            if entry.is_file():
                entries.append(entry)
        root_record["status"], root_record["entries_scanned"] = "scanned", len(entries)
        return entries, []
    except OSError as exc:
        root_record["status"] = "read-error"
        return [], [read_issue("scan-error", exc, root)]


def load_manifest(path):
    if path is None or not Path(path).exists():
        return {}, []
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_ENTRY_BYTES + 1)
        if len(raw) > MAX_ENTRY_BYTES:
            raise ValueError("Manifest exceeds the 1 MiB safety bound")
        content = json.loads(raw.decode("utf-8"))
        if content.get("schema_version") != 1 or not isinstance(content.get("upstreams"), list):
            raise ValueError("Manifest must use schema_version 1 and an upstreams array")
        entries = {}
        for entry in content["upstreams"]:
            if not isinstance(entry, dict) or entry.get("logical_name") not in EXPECTED:
                raise ValueError("Manifest has an unknown logical_name")
            logical = entry["logical_name"]
            if logical in entries or entry.get("expected_name") != EXPECTED[logical]:
                raise ValueError("Manifest duplicate logical_name or unexpected Skill name")
            if not re.fullmatch(r"[a-fA-F0-9]{64}", entry.get("entry_sha256", "")):
                raise ValueError("Manifest entry_sha256 must be a SHA-256 hash")
            entries[logical] = entry
        return entries, []
    except (OSError, ValueError, UnicodeDecodeError, AttributeError, TypeError) as exc:
        if isinstance(exc, OSError):
            return {}, [read_issue("manifest-read-error", exc, path)]
        return {}, [issue("manifest-invalid", str(exc), path)]


def candidate(entry, metadata, manifest):
    with entry.open("rb") as handle:
        raw = handle.read(MAX_ENTRY_BYTES + 1)
    if len(raw) > MAX_ENTRY_BYTES:
        raise ValueError("SKILL.md exceeds the 1 MiB safety bound")
    digest = hashlib.sha256(raw).hexdigest()
    nested = metadata.get("metadata", {})
    actual_version = nested.get("version") if isinstance(nested, dict) else None
    expected_digest = manifest.get("entry_sha256") if manifest else None
    matches = bool(expected_digest and expected_digest.lower() == digest)
    provenance = None
    if manifest:
        provenance = {key: manifest.get(key) for key in (
            "repository", "source_path", "checked_on", "upstream_entry_sha256", "local_modification")}
        provenance.update({
            "entry_hash_matches_manifest": matches,
            "source_version": manifest.get("version") if matches else None,
            "source_commit": manifest.get("commit") if matches else None,
        })
    return {
        "entry_path": str(entry.resolve()), "actual_name": metadata["name"],
        "actual_version": actual_version or "unknown", "entry_sha256": digest,
        "provenance": provenance,
        "drift": "changed" if expected_digest and not matches else ("matched" if matches else "untracked"),
    }


def entry_issue_dependencies(path, metadata=None):
    """Bound error attribution; these hints never identify available candidates.

    A conventional directory and an actual, known declared name must both be
    recognized before an entry problem can be isolated to an unrelated phase.
    For malformed headers, inspect every top-level name declaration using the
    same scalar parser. Unknown, missing, conflicting, or unreadable declarations
    remain unattributed and therefore fatal. No folder name replaces frontmatter.
    """
    reverse = {name: logical for logical, name in EXPECTED.items()}
    folder_logical = reverse.get(path.parent.name)
    if folder_logical is None:
        return None
    if metadata is not None:
        declared = metadata.get("name")
        if declared not in reverse:
            return None
        return sorted({folder_logical, reverse[declared]})
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_ENTRY_BYTES + 1)
        if len(raw) > MAX_ENTRY_BYTES:
            return None
        lines = raw.decode("utf-8").lstrip("\ufeff").splitlines()
        if not lines or lines[0] != "---":
            return None
        end = lines.index("---", 1) if "---" in lines[1:] else len(lines)
        names = []
        for line in lines[1:end]:
            if not line.startswith("name:"):
                continue
            # Parse one genuine declaration only to attribute an existing error;
            # synthetic description satisfies the parser's unrelated required key.
            declaration = parse_frontmatter("---\n%s\ndescription: Diagnostic name hint\n---\n" % line)
            names.append(declaration["name"])
        if len(names) != 1 or names[0] not in reverse:
            return None
        return sorted({folder_logical, reverse[names[0]]})
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def attributed_entry_issue(code, message, path, metadata=None):
    result = issue(code, message, path)
    affected = entry_issue_dependencies(path, metadata)
    if affected is not None:
        result["affected_dependencies"] = affected
    return result


def discover(roots, manifest=None):
    manifest = manifest or {}
    found = {key: [] for key in EXPECTED}
    errors, seen = [], set()
    reverse = {name: logical for logical, name in EXPECTED.items()}
    for root in roots:
        entries, scan_errors = entry_paths(root)
        errors.extend(scan_errors)
        for path in entries:
            metadata = None
            try:
                entry = path.resolve(strict=True)
                if entry in seen:
                    continue
                seen.add(entry)
                metadata = read_frontmatter(entry)
                logical = reverse.get(metadata["name"])
                if path.parent.name in reverse and metadata["name"] != path.parent.name:
                    errors.append(attributed_entry_issue("name-mismatch", "Expected %s but frontmatter declares %s" %
                                                         (path.parent.name, metadata["name"]), path, metadata))
                if logical:
                    found[logical].append(candidate(entry, metadata, manifest.get(logical)))
            except OSError as exc:
                errors.append(read_issue("entry-read-error", exc, path))
            except (ValueError, RuntimeError) as exc:
                errors.append(attributed_entry_issue("frontmatter-invalid", str(exc), path, metadata))
    dependencies = []
    for logical, expected in EXPECTED.items():
        candidates = sorted(found[logical], key=lambda item: item["entry_path"])
        status = "available" if len(candidates) == 1 else ("ambiguous" if candidates else "missing")
        dependencies.append({"logical_name": logical, "expected_name": expected,
                             "status": status, "candidates": candidates})
    return dependencies, errors


def _program(paths, fallback):
    for path in paths:
        if path.is_file():
            # Preserve the .venv executable symlink: resolving it to the base
            # interpreter would discard virtual-environment selection.
            return str(path.absolute())
    return shutil.which(fallback)


def _version_program(path, arguments, pattern):
    if not path:
        return {"status": "missing", "path": None, "version": "unknown"}
    try:
        completed = subprocess.run([path] + arguments, capture_output=True, text=True, timeout=10,
                                   encoding="utf-8", errors="replace")
        match = re.search(pattern, completed.stdout + completed.stderr)
        if completed.returncode != 0 or not match:
            return {"status": "failed", "path": path, "version": "unknown",
                    "message": "Fixed version probe failed or returned an unrecognized version"}
        return {"status": "available", "path": path, "version": match.group(1)}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "failed", "path": path, "version": "unknown", "message": "Fixed version probe could not run"}


def media_check(dependencies):
    oil = next(item for item in dependencies if item["logical_name"] == "oil-motion")
    if oil["status"] != "available":
        return {"status": "unavailable", "reason": "Resolve a unique oil-motion Skill first"}
    skill = Path(oil["candidates"][0]["entry_path"]).parent
    local_note = skill / "LOCAL-RUNTIME.md"
    venv = skill / ".venv"
    python_paths = [venv / "Scripts" / "python.exe", venv / "bin" / "python", venv / "bin" / "python3"]
    interpreter = _program(python_paths, "python3") or shutil.which("python")
    python = _version_program(interpreter, ["-I", "--version"], r"Python\s+([0-9]+\.[0-9]+\.[0-9]+)")
    if python["status"] == "available" and tuple(map(int, python["version"].split(".")[:2])) < (3, 10):
        python["status"], python["message"] = "unsupported", "Oil Motion requires Python 3.10+"
    native = {}
    for name in ("ffmpeg", "ffprobe"):
        paths = [venv / "Scripts" / (name + ".exe"), venv / "bin" / name,
                 skill / ".runtime" / "bin" / (name + ".exe"), skill / ".runtime" / "bin" / name]
        native[name] = _version_program(_program(paths, name), ["-version"],
                                        re.escape(name) + r"\s+version\s+(\S+)")
    # Inspect known immediate package metadata only; do not import PIL/.pth files.
    package_roots = [venv / "Lib" / "site-packages"]
    package_roots.extend(sorted((venv / "lib").glob("python*/site-packages"))[:8])
    pillow = {"status": "unknown", "version": "unknown", "verification": "metadata-only; import not executed"}
    try:
        for root in package_roots:
            for metadata_path in sorted(root.glob("[Pp]illow-*.dist-info/METADATA"))[:8]:
                with metadata_path.open("rb") as handle:
                    text = handle.read(65536).decode("utf-8")
                version = re.search(r"^Version:\s*(.+)$", text, re.MULTILINE)
                if version and (root / "PIL" / "__init__.py").is_file():
                    pillow.update(status="present", version=version.group(1), path=str(metadata_path.resolve()))
                    break
            if pillow["status"] == "present":
                break
    except (OSError, UnicodeDecodeError):
        pillow.update(status="failed", message="Could not read bounded Pillow metadata")
    checks = [python] + list(native.values())
    status = "available" if all(item["status"] == "available" for item in checks) and pillow["status"] == "present" else "unavailable"
    return {"status": status, "python": python, **native, "pillow": pillow,
            "local_runtime": {"venv_present": venv.is_dir(), "venv_path": str(venv.resolve()) if venv.is_dir() else None,
                              "note_present": local_note.is_file(), "note_path": str(local_note.resolve()) if local_note.is_file() else None},
            "limitation": "Version/presence checks only; no media pipeline or generation service was executed"}


def redact_paths(value):
    if isinstance(value, dict):
        return {key: redact_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    if isinstance(value, str) and (os.path.isabs(value) or PureWindowsPath(value).is_absolute()):
        return "<local-path>"
    return value


def run(args):
    project = _resolved(args.project)
    result = {"schema_version": 1, "checked_on": datetime.now(timezone.utc).date().isoformat(),
              "requirements": [], "roots": [], "dependencies": [], "media": {"status": "not-requested"}, "errors": [],
              "warnings": []}
    requirements = []
    for given in (args.require or list(EXPECTED)):
        logical = ALIASES.get(given, given)
        if logical not in EXPECTED:
            result["errors"].append(issue("invalid-requirement", "Unknown logical Skill: %s" % given))
        elif logical not in requirements:
            requirements.append(logical)
    result["requirements"] = requirements
    if not project.is_dir():
        result["errors"].append(issue("invalid-project", "Project must be an existing directory", project))
    if args.media and "oil-motion" not in requirements:
        requirements.append("oil-motion")
    if result["errors"]:
        result["summary"] = {"status": "error", "exit_code": 1}
        return result, 1
    manifest_path = Path(args.manifest) if args.manifest else Path(__file__).resolve().parent.parent / "references" / "upstreams.json"
    if args.manifest and not manifest_path.is_file():
        result["errors"].append(issue("invalid-manifest", "Explicit manifest must be an existing file", _resolved(manifest_path)))
    manifest, manifest_errors = load_manifest(manifest_path)
    result["errors"].extend(manifest_errors)
    try:
        result["roots"] = search_roots(project, args.skill_root)
        result["dependencies"], errors = discover(result["roots"], manifest)
        for entry_problem in errors:
            affected = entry_problem.get("affected_dependencies")
            if affected and not set(affected).intersection(requirements):
                result["warnings"].append({**entry_problem, "reason": "not-required-for-this-phase"})
            else:
                result["errors"].append(entry_problem)
        if args.media:
            result["media"] = media_check(result["dependencies"])
    except (OSError, ValueError, RuntimeError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        result["errors"].append(issue("discovery-error", message))
    unavailable = [item["logical_name"] for item in result["dependencies"]
                   if item["logical_name"] in requirements and item["status"] != "available"]
    exit_code = 1 if result["errors"] else (2 if unavailable or (args.media and result["media"]["status"] != "available") else 0)
    result["summary"] = {"status": "error" if exit_code == 1 else ("unavailable" if exit_code == 2 else "available"),
                         "unavailable_requirements": unavailable, "exit_code": exit_code}
    return result, exit_code


class InputParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = InputParser(description=__doc__)
    parser.add_argument("--project", default=str(Path.cwd()), help="Existing project directory; ancestor discovery stops at the nearest Git root")
    parser.add_argument("--skill-root", action="append", default=[], help="Additional Skill container or direct Skill directory; repeatable, bounded")
    parser.add_argument("--require", action="append", help="Required logical Skill: taste, impeccable, oil-motion; repeatable (default all three)")
    parser.add_argument("--manifest", help="Optional explicit provenance manifest (default references/upstreams.json if present)")
    parser.add_argument("--media", action="store_true", help="Check Oil Motion local Python, Pillow metadata, ffmpeg and ffprobe; never credentials")
    parser.add_argument("--shareable", action="store_true", help="Redact absolute local paths from JSON output")
    try:
        args = parser.parse_args(argv)
    except ValueError as exc:
        print(json.dumps({"schema_version": 1, "errors": [issue("invalid-arguments", str(exc))],
                          "summary": {"status": "error", "exit_code": 1}}, ensure_ascii=False, indent=2))
        return 1
    try:
        result, code = run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        result, code = {"schema_version": 1, "errors": [issue("input-or-read-error", type(exc).__name__)],
                        "summary": {"status": "error", "exit_code": 1}}, 1
    if args.shareable:
        result = redact_paths(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

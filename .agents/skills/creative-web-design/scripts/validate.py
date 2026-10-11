#!/usr/bin/env python3
"""Validate custom orchestration data; optionally run a reviewed official validator.

This is package/schema validation, not a visual score, Codex activation test,
browser acceptance test, permission boundary, or third-party skill invocation.
Only an explicitly supplied --official-validator script is executed.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

try:
    from skill_utils import read_frontmatter
except ImportError:
    def read_frontmatter(path):
        raise ValueError("Required local helper scripts/skill_utils.py is unavailable")


NAME = "creative-web-design"
MODES = ["auto", "explore", "build", "refine", "motion", "review"]
TASK_KINDS = ["creative-site", "frontend-change", "animation", "review", "backend", "copy"]
ANIMATIONS = ["none", "native", "realtime", "existing-media", "generate-media"]
STATUSES = ["planned", "read", "executed", "verified", "skipped", "blocked", "not-run"]
DIRECTION_STATUSES = ["unconfirmed", "user-confirmed", "user-delegated", "existing"]
REQUIRED = [
    "SKILL.md", "agents/openai.yaml", "references/workflow.md",
    "references/creative-direction.md", "references/integrations.md",
    "references/quality-gates.md", "references/upstreams.json",
    "references/routes.json", "references/installation.md", "assets/templates/brief.md",
    "assets/templates/art-direction.md", "assets/templates/session.json",
    "scripts/doctor.py", "scripts/validate.py", "scripts/workflow.py", "scripts/skill_utils.py",
]
SECRET_KEYS = {"api_key", "apikey", "access_token", "bearer_token", "client_secret",
               "password", "secret", "private_key", "zenmux_api_key"}
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.I)


def safe_relative(value):
    """Accept portable project-relative paths; reject drive/UNC/traversal paths."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    path = value.replace("\\", "/")
    return not (path.startswith("/") or re.match(r"^[A-Za-z]:", path)
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path) or ".." in PurePosixPath(path).parts)


def valid_cost(value):
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def load_json(path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append("{}: {}".format(path.name, exc))
        return None


def secret_fields(value, errors, label="session"):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in SECRET_KEYS or normalized.endswith("_api_key"):
                errors.append("{} contains forbidden credential field {}".format(label, key))
            secret_fields(child, errors, label + "." + key)
    elif isinstance(value, list):
        for child in value:
            secret_fields(child, errors, label)


def validate_session(path):
    """Validate recoverable custom session fields, grants, paths and evidence."""
    errors = []
    data = load_json(Path(path), errors)
    if not isinstance(data, dict):
        if data is not None:
            errors.append("session must be a JSON object")
        return errors
    secret_fields(data, errors)
    required = {"schema_version", "run_id", "task", "mode", "scope", "current_stage",
                "direction", "dependencies", "authorization", "artifacts", "checks",
                "blocked", "next_step", "evidence"}
    for key in sorted(required - data.keys()):
        errors.append("session missing " + key)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("session schema_version must be 1")
    if data.get("mode") not in MODES:
        errors.append("session mode is invalid")
    for key in ("run_id", "task", "next_step"):
        if data.get(key) is not None and not isinstance(data.get(key), str):
            errors.append("session {} must be string or null".format(key))
    if not isinstance(data.get("current_stage"), str) or not data.get("current_stage", "").strip():
        errors.append("session current_stage must be nonempty string")
    scope = data.get("scope")
    if not isinstance(scope, dict):
        errors.append("session scope must be object")
    else:
        for key in ("allowed_paths", "preserve", "target_devices"):
            values = scope.get(key)
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                errors.append("scope.{} must be list of strings".format(key))
            elif key == "allowed_paths" and any(not safe_relative(x) for x in values):
                errors.append("scope.allowed_paths must contain safe relative paths")
    direction = data.get("direction")
    direction_status = None
    if not isinstance(direction, dict):
        errors.append("session direction must be object")
    else:
        for key in ("status", "file", "confirmation_source"):
            if key not in direction:
                errors.append("direction missing " + key)
        direction_status = direction.get("status")
        if direction_status not in DIRECTION_STATUSES:
            errors.append("direction.status is invalid")
        reference = direction.get("file")
        if reference is not None and not safe_relative(reference):
            errors.append("direction.file must be safe relative path or null")
        source = direction.get("confirmation_source")
        if source is not None and (not isinstance(source, str) or not source.strip()):
            errors.append("direction.confirmation_source must be nonempty string or null")
        if direction_status in ("user-confirmed", "user-delegated"):
            if reference is None or not isinstance(source, str) or not source.strip():
                errors.append("confirmed or delegated direction requires file and user confirmation source")
        if direction_status == "existing" and reference is None:
            errors.append("existing direction requires a relative direction file")
        if direction_status == "unconfirmed" and source is not None:
            errors.append("unconfirmed direction cannot claim a confirmation source")
    authorization = data.get("authorization")
    implementation = False
    if not isinstance(authorization, dict):
        errors.append("session authorization must be object")
    else:
        implementation = authorization.get("implementation")
        if type(implementation) is not bool:
            errors.append("authorization.implementation must be boolean")
        if implementation is True and data.get("mode") in ("explore", "review"):
            errors.append("explore/review cannot authorize formal business implementation")
        generation = authorization.get("generation")
        if not isinstance(generation, dict):
            errors.append("authorization.generation must be object")
        else:
            for key in ("status", "service", "data_scope", "max_calls", "max_cost", "currency", "stop_conditions"):
                if key not in generation:
                    errors.append("generation missing " + key)
            generation_status = generation.get("status")
            if generation_status not in ("not-requested", "missing", "granted", "blocked", "not-run", "revoked", "exhausted"):
                errors.append("generation.status is invalid")
            for key in ("service", "currency"):
                if generation.get(key) is not None and (not isinstance(generation[key], str) or not generation[key].strip()):
                    errors.append("generation.{} must be nonempty string or null".format(key))
            for key in ("data_scope", "stop_conditions"):
                values = generation.get(key)
                if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
                    errors.append("generation.{} must be list of nonempty strings".format(key))
            calls = generation.get("max_calls")
            cost = generation.get("max_cost")
            if calls is not None and (type(calls) is not int or calls < 0):
                errors.append("generation.max_calls must be nonnegative integer or null")
            if cost is not None and not valid_cost(cost):
                errors.append("generation.max_cost must be nonnegative number or null")
            if generation_status == "granted":
                if not generation.get("service") or not generation.get("data_scope") or not generation.get("stop_conditions"):
                    errors.append("granted generation requires service, data scope and stop conditions")
                has_calls = type(calls) is int and calls > 0
                has_cost = valid_cost(cost) and cost > 0
                if not has_calls and not has_cost:
                    errors.append("granted generation requires a positive call or cost budget")
                if has_cost and not generation.get("currency"):
                    errors.append("generation cost budget requires currency")
    if implementation is True and data.get("mode") in ("build", "refine") and direction_status == "unconfirmed":
        errors.append("build/refine implementation requires a locked direction")
    if implementation is True and isinstance(scope, dict) and not scope.get("allowed_paths"):
        errors.append("implementation authorization requires explicit allowed_paths scope")
    any_blocked = False
    for key in ("dependencies", "artifacts", "checks", "blocked", "evidence"):
        if not isinstance(data.get(key), list):
            errors.append("session {} must be list".format(key))
    for key in ("dependencies", "artifacts", "checks", "stages"):
        values = data.get(key, [])
        if not isinstance(values, list):
            errors.append("session {} must be list".format(key))
            continue
        for index, item in enumerate(values):
            label = "{}[{}]".format(key, index)
            if not isinstance(item, dict):
                errors.append(label + " must be object")
                continue
            if "status" in item:
                status = item["status"]
                if status not in STATUSES:
                    errors.append(label + ".status is invalid")
                if status == "verified":
                    evidence = item.get("evidence")
                    if not isinstance(evidence, list) or not evidence or any(not isinstance(x, str) or not x.strip() for x in evidence):
                        errors.append(label + " verified status requires evidence as a nonempty list of references")
                    elif any(not safe_relative(x) for x in evidence):
                        errors.append(label + " evidence references must be safe relative paths")
                any_blocked = any_blocked or status == "blocked"
            elif key in ("checks", "stages"):
                errors.append(label + " requires status")
            if key == "artifacts":
                reference = item.get("path")
                if not safe_relative(reference):
                    errors.append(label + ".path must be safe relative path")
    for index, item in enumerate(data.get("evidence", []) if isinstance(data.get("evidence"), list) else []):
        label = "evidence[{}]".format(index)
        if not isinstance(item, dict):
            errors.append(label + " must be object")
            continue
        if not safe_relative(item.get("path")):
            errors.append(label + ".path must be safe relative path")
        if not isinstance(item.get("sha256"), str) or not HEX64.fullmatch(item["sha256"]):
            errors.append(label + ".sha256 must be 64 hexadecimal characters")
        stages = item.get("affects_stages")
        if not isinstance(stages, list) or any(not isinstance(x, str) for x in stages):
            errors.append(label + ".affects_stages must be list of stage names")
    if data.get("current_stage") in ("complete", "completed", "done") and (data.get("blocked") or any_blocked):
        errors.append("session cannot claim completion with unresolved blocked items")
    return errors


def validate_openai(path, errors):
    """Read the deliberately small generated YAML subset without dependencies."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append("agents/openai.yaml: " + str(exc))
        return
    parsed = {}
    section = None
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = re.fullmatch(r"([a-z_]+):\s*", line)
        if top:
            section = top.group(1)
            if section in parsed:
                errors.append("openai.yaml duplicate section " + section)
            parsed[section] = {}
            continue
        field = re.fullmatch(r"  ([a-z_]+):\s*(.*?)\s*", line)
        if not field or section is None:
            errors.append("openai.yaml unsupported structure at line {}".format(number))
            continue
        key, raw = field.groups()
        if key in parsed[section]:
            errors.append("openai.yaml duplicate field " + key)
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                errors.append("openai.yaml invalid quoted string at line {}".format(number))
                continue
        elif raw.startswith("'") and raw.endswith("'"):
            value = raw[1:-1].replace("''", "'")
        elif raw in ("true", "false"):
            value = raw == "true"
        else:
            errors.append("openai.yaml strings must be quoted at line {}".format(number))
            continue
        parsed[section][key] = value
    if set(parsed) != {"interface", "policy"}:
        errors.append("openai.yaml only interface and policy are supported; child skills are not MCP dependencies.tools")
    interface = parsed.get("interface", {})
    if set(interface) != {"display_name", "short_description", "default_prompt"}:
        errors.append("openai.yaml interface requires only display_name, short_description and default_prompt")
    for key in ("display_name", "short_description", "default_prompt"):
        if not isinstance(interface.get(key), str) or not interface.get(key, "").strip():
            errors.append("openai.yaml interface.{} must be nonempty string".format(key))
    short = interface.get("short_description", "")
    if isinstance(short, str) and not 25 <= len(short) <= 64:
        errors.append("openai.yaml short_description must have 25-64 characters")
    if "$creative-web-design" not in str(interface.get("default_prompt", "")):
        errors.append("openai.yaml default_prompt must include literal $creative-web-design")
    if parsed.get("policy") != {"allow_implicit_invocation": False}:
        errors.append("openai.yaml requires policy.allow_implicit_invocation: false")


def validate_manifest(path, errors):
    data = load_json(path, errors)
    if not isinstance(data, dict):
        if data is not None:
            errors.append("upstreams.json must be object")
        return
    secret_fields(data, errors, "upstreams")
    def paths(value):
        if isinstance(value, dict):
            for child in value.values():
                paths(child)
        elif isinstance(value, list):
            for child in value:
                paths(child)
        elif isinstance(value, str) and (value.startswith(("/", "\\\\", "file://", "~/")) or re.match(r"^[A-Za-z]:[\\/]", value)):
            errors.append("upstreams.json must not contain local absolute filesystem paths")
    paths(data)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("upstreams schema_version must be 1")
    expected = {"taste": "design-taste-frontend", "impeccable": "impeccable", "oil-motion": "oil-motion"}
    upstreams = data.get("upstreams")
    if not isinstance(upstreams, list):
        errors.append("upstreams must be list")
        return
    seen = []
    for index, entry in enumerate(upstreams):
        label = "upstreams[{}]".format(index)
        if not isinstance(entry, dict):
            errors.append(label + " must be object")
            continue
        logical = entry.get("logical_name")
        if not isinstance(logical, str):
            errors.append(label + ".logical_name must be string")
            logical = ""
        seen.append(logical)
        if logical not in expected or entry.get("expected_name") != expected.get(logical):
            errors.append(label + " invalid logical_name/expected_name")
        for key in ("repository", "source_path", "version", "commit", "entry_sha256", "upstream_entry_sha256", "checked_on"):
            if key not in entry:
                errors.append(label + " missing " + key)
        repository = entry.get("repository")
        valid_repository = False
        if isinstance(repository, str):
            try:
                parsed = urlsplit(repository)
                valid_repository = parsed.scheme in ("https", "http") and bool(parsed.netloc)
            except ValueError:
                pass
        if not valid_repository:
            errors.append(label + ".repository must be source URL")
        if not safe_relative(entry.get("source_path")):
            errors.append(label + ".source_path must be portable relative path")
        if entry.get("version") is not None and (not isinstance(entry["version"], str) or not entry["version"].strip()):
            errors.append(label + ".version must be nonempty string or null")
        if entry.get("commit") is not None and (not isinstance(entry["commit"], str) or not HEX40.fullmatch(entry["commit"])):
            errors.append(label + ".commit must be full 40-character SHA or null")
        for key in ("entry_sha256", "upstream_entry_sha256"):
            value = entry.get(key)
            if value is not None and (not isinstance(value, str) or not HEX64.fullmatch(value)):
                errors.append(label + ".{} must be SHA256 or null".format(key))
        if not isinstance(entry.get("checked_on"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.get("checked_on", "")):
            errors.append(label + ".checked_on must use YYYY-MM-DD")
    if len(seen) != 3 or set(seen) != set(expected):
        errors.append("upstreams must contain exactly taste, impeccable and oil-motion once")


def validate_routes(path, errors):
    data = load_json(path, errors)
    expected = {"schema_version": 1, "modes": MODES, "task_kinds": TASK_KINDS,
                "animations": ANIMATIONS, "stage_statuses": STATUSES,
                "direction_statuses": DIRECTION_STATUSES}
    if not isinstance(data, dict):
        if data is not None:
            errors.append("routes.json must be object")
        return
    for key, value in expected.items():
        if data.get(key) != value or (key == "schema_version" and type(data.get(key)) is not int):
            errors.append("routes.{} does not match supported contract".format(key))


def headings(path):
    anchors = set()
    counts = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^#{1,6}\s+", line):
            text = re.sub(r"^#{1,6}\s+", "", line).strip().rstrip("#").strip()
            slug = re.sub(r"[^\w\-\s]", "", text.lower()).replace(" ", "-")
            number = counts.get(slug, 0)
            counts[slug] = number + 1
            anchors.add(slug if number == 0 else "{}-{}".format(slug, number))
    return anchors


def validate_links(root, errors):
    """Check inline and reference Markdown destinations outside fenced examples."""
    for path in sorted(root.rglob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            content = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", content)
            destinations = re.findall(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+['\"][^)]*)?\)", content)
            destinations += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", content)
            for destination in destinations:
                destination = unquote(destination.strip("<>"))
                parsed = urlsplit(destination)
                if parsed.scheme in ("http", "https", "mailto", "app", "plugin"):
                    continue
                filename, separator, anchor = destination.partition("#")
                if filename and (filename.replace("\\", "/").startswith("/") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", filename) or "\x00" in filename):
                    errors.append("{}: unsafe internal reference {}".format(path.relative_to(root), destination))
                    continue
                target = (path.parent / filename).resolve() if filename else path.resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    errors.append("{}: internal reference escapes skill {}".format(path.relative_to(root), destination))
                    continue
                if not target.exists():
                    errors.append("{}: missing internal reference {}".format(path.relative_to(root), destination))
                elif separator and anchor and target.suffix.lower() == ".md" and anchor not in headings(target):
                    errors.append("{}: missing anchor {}".format(path.relative_to(root), destination))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append("{}: {}".format(path.name, exc))


def validate_package(path):
    root = Path(path).resolve()
    errors = []
    warnings = []
    for relative in REQUIRED:
        if not (root / relative).is_file():
            errors.append("missing required file " + relative)
        else:
            try:
                (root / relative).resolve().relative_to(root)
            except ValueError:
                errors.append("required file escapes package through symlink " + relative)
    entry = root / "SKILL.md"
    if entry.is_file():
        try:
            frontmatter = read_frontmatter(entry)
            name = frontmatter.get("name")
            if name != NAME or not isinstance(name, str) or len(name) > 64:
                errors.append("SKILL.md name must be creative-web-design (max 64 characters)")
            description = frontmatter.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                errors.append("SKILL.md description must be nonempty and at most 1024 characters")
            elif "<" in description or ">" in description or "[TODO:" in description:
                errors.append("SKILL.md description contains prohibited placeholder or angle brackets")
            allowed = {"name", "description", "license", "allowed-tools", "metadata"}
            if set(frontmatter) - allowed:
                errors.append("SKILL.md has unsupported frontmatter keys")
            metadata = frontmatter.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                errors.append("SKILL.md metadata must be mapping")
            elif isinstance(metadata, dict) and "version" in metadata and not isinstance(metadata["version"], str):
                errors.append("SKILL.md metadata.version must be string")
            content = entry.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*\[TODO:", content):
                errors.append("SKILL.md contains unfinished TODO instructions")
            if len(content.splitlines()) > 220:
                warnings.append("SKILL.md exceeds the recommended roughly 200 lines")
        except (ValueError, OSError, UnicodeError) as exc:
            errors.append("SKILL.md: " + str(exc))
    if (root / "agents/openai.yaml").is_file():
        validate_openai(root / "agents/openai.yaml", errors)
    for relative, validator in (("references/upstreams.json", validate_manifest), ("references/routes.json", validate_routes)):
        if (root / relative).is_file():
            validator(root / relative, errors)
    if (root / "assets/templates/session.json").is_file():
        errors.extend("session template: " + message for message in validate_session(root / "assets/templates/session.json"))
    validate_links(root, errors)
    return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}


def official_check(script, skill):
    if script is None:
        return {"status": "not-run", "reason": "No explicit reviewed --official-validator path supplied"}
    path = Path(script).expanduser().resolve()
    if not path.is_file() or path.suffix != ".py":
        return {"status": "not-run", "reason": "Explicit validator must be an existing Python file"}
    if importlib.util.find_spec("yaml") is None:
        return {"status": "not-run", "reason": "PyYAML is unavailable in this interpreter; environment was not modified"}
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, str(path), str(skill)], capture_output=True,
                                text=True, timeout=30, check=False)
        return {"status": "passed" if result.returncode == 0 else "failed", "path": str(path),
                "script_sha256": digest,
                "exit_code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "not-run", "reason": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--official-validator", type=Path, help="Explicit path to an already reviewed local official Python validator")
    parser.add_argument("--session", type=Path, help="Also validate a custom session JSON file")
    args = parser.parse_args(argv)
    result = validate_package(args.skill_path)
    if args.session:
        result["errors"].extend(validate_session(args.session))
        result["status"] = "failed" if result["errors"] else "passed"
    official = official_check(args.official_validator, args.skill_path.resolve())
    report = {"validator": "creative-web-design-custom", "scope": "Custom package metadata, local references, manifest, route and session schemas only; no visual or activation acceptance", "custom": result, "official": official}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "failed" or official["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())

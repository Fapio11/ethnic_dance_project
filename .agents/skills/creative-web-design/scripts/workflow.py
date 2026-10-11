#!/usr/bin/env python3
"""Read-only deterministic planning and evidence comparison, Python 3.9+.

The principal agent supplies structured intent. This program does not infer user
authorization from prose, invoke skills, execute commands, or enforce a sandbox.
Exit codes: 0 = report ready, 1 = invalid input, 2 = plan has a checkpoint.
"""

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


ROUTES = {
    "schema_version": 1,
    "modes": ["auto", "explore", "build", "refine", "motion", "review"],
    "task_kinds": ["creative-site", "frontend-change", "animation", "review", "backend", "copy"],
    "animations": ["none", "native", "realtime", "existing-media", "generate-media"],
    "stage_statuses": ["planned", "read", "executed", "verified", "skipped", "blocked", "not-run"],
    "direction_statuses": ["unconfirmed", "user-confirmed", "user-delegated", "existing"],
}
ENHANCEMENTS = {
    "animate", "delight", "overdrive", "polish", "harden", "adapt", "optimize",
    "clarify", "distill", "colorize", "extract", "bolder", "quieter",
    "layout", "typeset", "onboard",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_routes():
    path = Path(__file__).resolve().parent.parent / "references" / "routes.json"
    if not path.exists() and not path.is_symlink():
        return copy.deepcopy(ROUTES)
    config = read_json(path)
    require(isinstance(config, dict) and config.get("schema_version") == 1,
            "routes.json: schema_version must be 1")
    for key, values in ROUTES.items():
        if key == "schema_version":
            continue
        actual = config.get(key)
        require(isinstance(actual, list) and all(isinstance(x, str) for x in actual)
                and len(actual) == len(set(actual)) and set(actual) == set(values),
                "routes.json: unsupported or incomplete " + key)
    return config


def strings(value, name):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value),
            name + " must be an array of nonempty strings")


def nullable_string(value, name):
    require(value is None or isinstance(value, str) and bool(value.strip()),
            name + " must be null or a nonempty string")


def validate_scope(scope):
    require(isinstance(scope, dict), "scope must be an object")
    for key in ("allowed_paths", "preserve", "target_devices"):
        strings(scope.get(key), "scope." + key)
    for index, reference in enumerate(scope["allowed_paths"]):
        relative_path(reference, "scope.allowed_paths[{}]".format(index))


def relative_path(reference, label):
    """Validate lexical portability; only resume has a root for symlink checks."""
    require(isinstance(reference, str) and reference.strip() and "\x00" not in reference,
            label + " must be a nonempty project-relative path")
    windows = PureWindowsPath(reference)
    parts = reference.replace("\\", "/").split("/")
    require(not PurePosixPath(reference).is_absolute() and not windows.drive
            and not windows.root and ".." not in parts, label + " cannot be absolute or traverse outside the project")
    return parts


def validate_authorization(auth):
    require(isinstance(auth, dict), "authorization must be an object")
    require(type(auth.get("implementation")) is bool,
            "authorization.implementation must be a boolean")
    gen = auth.get("generation")
    require(isinstance(gen, dict), "authorization.generation must be an object")
    require(gen.get("status") in ("not-requested", "granted", "missing"),
            "authorization.generation.status is invalid")
    nullable_string(gen.get("service"), "authorization.generation.service")
    nullable_string(gen.get("currency"), "authorization.generation.currency")
    strings(gen.get("data_scope"), "authorization.generation.data_scope")
    strings(gen.get("stop_conditions"), "authorization.generation.stop_conditions")
    calls = gen.get("max_calls")
    cost = gen.get("max_cost")
    require(calls is None or type(calls) is int and calls >= 0,
            "authorization.generation.max_calls must be null or a nonnegative integer")
    require(cost is None or type(cost) is int and cost >= 0
            or type(cost) is float and math.isfinite(cost) and cost >= 0,
            "authorization.generation.max_cost must be null or a finite nonnegative number")


def validate_intent(intent, routes):
    require(isinstance(intent, dict), "intent must be an object")
    for key, options in (("mode", "modes"), ("task_kind", "task_kinds"), ("animation", "animations")):
        require(intent.get(key) in routes[options], key + " is missing or unsupported")
    direction = intent.get("direction")
    require(isinstance(direction, dict), "direction must be an object")
    require(direction.get("status") in routes["direction_statuses"], "direction.status is invalid")
    nullable_string(direction.get("reference"), "direction.reference")
    if direction.get("reference") is not None:
        relative_path(direction["reference"], "direction.reference")
    validate_scope(intent.get("scope"))
    validate_authorization(intent.get("authorization"))
    strings(intent.get("desired_enhancements", []), "desired_enhancements")
    require(set(intent.get("desired_enhancements", [])) <= ENHANCEMENTS,
            "desired_enhancements contains an unsupported capability")


def generation_reasons(grant):
    reasons = []
    if grant["status"] != "granted":
        reasons.append("generation authorization is not granted")
    if not grant.get("service"):
        reasons.append("generation service is unspecified")
    if not grant["data_scope"]:
        reasons.append("authorized data scope is unspecified")
    has_calls = grant.get("max_calls") is not None and grant["max_calls"] > 0
    has_cost = grant.get("max_cost") is not None and grant["max_cost"] > 0
    if not has_calls and not has_cost:
        reasons.append("a positive call or cost budget is required")
    if has_cost and not grant.get("currency"):
        reasons.append("cost budget currency is unspecified")
    if not grant["stop_conditions"]:
        reasons.append("generation stop conditions are unspecified")
    return reasons


def select_mode(intent):
    if intent["task_kind"] == "review":
        return "review"
    if intent["mode"] != "auto":
        return intent["mode"]
    if intent["task_kind"] == "animation":
        return "motion"
    if intent["task_kind"] == "frontend-change":
        return "motion" if intent["animation"] != "none" else "refine"
    if intent["direction"]["status"] != "unconfirmed" and intent["authorization"]["implementation"]:
        return "build"
    return "explore"


def plan(intent):
    """Produce a proposal only; an agent must read and execute any scheduled step."""
    validate_intent(intent, load_routes())
    intent = copy.deepcopy(intent)
    intent.setdefault("desired_enhancements", [])
    eligible = intent["task_kind"] not in ("backend", "copy")
    mode = select_mode(intent) if eligible else None
    result = {
        "schema_version": 1, "eligible": eligible, "requested_mode": intent["mode"],
        "effective_mode": mode, "intent": intent, "scope": copy.deepcopy(intent["scope"]),
        "direction_checkpoint": False, "stage_plan": [], "blocked": [], "skipped": [],
        "generation": {"route": "none", "status": "not-requested", "reasons": [], "continuation": []},
        "next_step": None,
        "warnings": ["This read-only proposal does not execute skills or enforce permissions, uploads, or spending."],
    }
    if not eligible:
        result["skipped"].append({"operation": "creative-web-design", "reason": "task kind is outside this skill"})
        result["next_step"] = "Use the appropriate backend or writing workflow."
        return result

    def stage(stage_id, actions, reads=(), capabilities=(), writes=False, reason=""):
        result["stage_plan"].append({
            "id": stage_id, "status": "planned", "requested_reads": list(reads),
            "requested_capabilities": list(capabilities), "actions": list(actions),
            "allowed_business_writes": writes, "reason": reason,
        })

    def checkpoint(operation, reason):
        result["blocked"].append({"operation": operation, "reason": reason})

    stage("intake", ["Read project constraints and the requested scope; resolve only needed dependencies."])
    if mode == "review":
        stage("bounded-review", ["Inspect evidence and report defects separately from intentional expression; do not apply fixes."],
              ["impeccable"], ["audit", "critique"])
        if intent["animation"] in ("existing-media", "generate-media"):
            stage("media-specification", ["Inspect existing media or document missing media; do not generate, process, or integrate assets."], ["oil-motion"])
        result["generation"]["status"] = "not-run"
        result["skipped"].append({"operation": "mutation", "reason": "review is read-only, even when prior authorization exists"})
        result["next_step"] = "Perform the scoped read-only review and record real evidence."
        return result

    direction = intent["direction"]["status"]
    needs_direction = mode == "build" and direction == "unconfirmed"
    if mode == "explore" or needs_direction:
        if direction in ("unconfirmed", "user-delegated"):
            stage("reference-exploration", ["Compare 2–3 concepts with different spatial or narrative mechanisms in isolated prototypes."], ["design-taste-frontend"])
        else:
            stage("reference-exploration", ["Explore only the requested fragment within the supplied direction; preserve its recorded features."], ["design-taste-frontend"])
        stage("direction-lock", ["Record creative features, adjustable details, prohibited regressions, references, and confirmation source."], ["design-taste-frontend"])
    elif mode == "build":
        action = ("Select a recommended direction within the user's explicitly delegated brief; record delegation and creative-preservation rules before implementation."
                  if direction == "user-delegated" else
                  "Read the confirmed or existing direction and carry it into implementation; do not reopen style selection.")
        stage("direction-lock", [action], ["design-taste-frontend"])
    if needs_direction:
        result["direction_checkpoint"] = True
        checkpoint("business-implementation", "direction is unconfirmed; implementation authorization does not imply authorization to select the direction")

    writes = mode != "explore" and intent["authorization"]["implementation"] and not needs_direction
    if mode != "explore" and not intent["authorization"]["implementation"]:
        checkpoint("business-implementation", "implementation authorization is missing; continue read-only planning")
    if writes and not intent["scope"]["allowed_paths"]:
        writes = False
        checkpoint("business-implementation", "allowed_paths is empty; define the scoped write targets before changing business files")
    if mode in ("build", "refine") and writes:
        stage("implementation-slice", ["Implement one representative scoped fragment using the existing stack and preserve every recorded feature and business constraint."],
              writes=True, reason="refine does not require a new brand or full creative pipeline" if mode == "refine" else "")

    animation = intent["animation"]
    if animation in ("native", "realtime"):
        stage("native-motion" if animation == "native" else "realtime-motion",
              ["Use the existing CSS/SVG/motion stack." if animation == "native" else "Use a single existing realtime controller for spatial or shader changes.",
               "Assign each animated property one controller and preserve usable fallback states."],
              writes=writes, reason="No media-generation route is needed; explore may use isolated prototypes only.")
    if animation in ("existing-media", "generate-media"):
        stage("media-specification", ["Read Oil Motion's actual required references; derive subject, continuity, interaction, timeline, and fallback specifications."], ["oil-motion"])
        result["generation"]["continuation"] = ["storyboard", "media specification", "existing resource analysis", "local work within authorized scope"]
        if animation == "existing-media":
            result["generation"].update({"route": "existing-media-local", "status": "not-requested"})
            stage("media-local-processing", ["Inspect existing media and plan local processing; do not regenerate or require a generation key."], ["oil-motion"], writes=writes)
        else:
            reasons = generation_reasons(intent["authorization"]["generation"])
            result["generation"].update({"route": "new-media", "status": "blocked" if reasons else "planned", "reasons": reasons})
            if reasons:
                checkpoint("external-media-generation", "; ".join(reasons))
            else:
                stage("media-generation", ["Produce at most one sample within the existing service, data, budget, and stop conditions; verify it before any batch."], ["oil-motion"], reason="Budget records are not a spending sandbox; use controlled credentials and actual host permissions.")
        if writes:
            stage("motion-integration", ["Integrate an available sample into the real page after checking content and continuity; keep controls as native page elements."], ["oil-motion"], writes=True,
                  reason="Generation blocking does not authorize pretending missing assets exist.")

    for capability in dict.fromkeys(intent["desired_enhancements"]):
        if writes:
            stage("enhancement-" + capability, ["Apply only the requested local " + capability + " task, preserving the locked identity and scope."],
                  ["impeccable"], [capability], writes=True)
        else:
            result["skipped"].append({"operation": "enhancement-" + capability, "reason": "business mutation is unavailable in this plan"})
    if mode in ("build", "refine"):
        stage("bounded-review", ["Read the corresponding installed review instructions; separate real defects from the chosen expression and report evidence."], ["impeccable"], ["audit", "critique"])
    stage("browser-verification", ["When a runnable fragment exists, inspect actual target-device views and trigger relevant interactions; record unavailable checks as not-run."])
    if mode == "explore":
        result["skipped"].append({"operation": "business-implementation", "reason": "explore ends with concepts or isolated prototypes; it does not modify formal pages"})
    result["next_step"] = "Perform the first planned stage; preserve prior authorization and recorded direction."
    return result


def project_path(root, reference, label):
    parts = relative_path(reference, label)
    candidate = root.joinpath(*parts)
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        raise ValueError(label + " resolves outside the project")
    return candidate


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resume(session, project):
    """Compare recorded file evidence; never rewrite the session or project."""
    routes = load_routes()
    require(isinstance(session, dict) and session.get("schema_version") == 1, "session.schema_version must be 1")
    require(session.get("mode") in routes["modes"], "session.mode is invalid")
    validate_scope(session.get("scope"))
    validate_authorization(session.get("authorization"))
    direction = session.get("direction")
    require(isinstance(direction, dict) and direction.get("status") in routes["direction_statuses"], "session.direction.status is invalid")
    nullable_string(direction.get("file"), "session.direction.file")
    evidence = session.get("evidence")
    require(isinstance(evidence, list), "session.evidence must be an array")
    root = Path(project).resolve()
    require(root.is_dir(), "project must be an existing directory")
    if direction.get("file"):
        project_path(root, direction["file"], "session.direction.file")
    changes, stages, seen, unchanged = [], [], set(), 0
    for index, item in enumerate(evidence):
        label = "session.evidence[{}]".format(index)
        require(isinstance(item, dict), label + " must be an object")
        path = project_path(root, item.get("path"), label + ".path")
        canonical = path.resolve()
        require(canonical not in seen, label + ": duplicate evidence path")
        seen.add(canonical)
        baseline = item.get("sha256")
        require(isinstance(baseline, str) and re.fullmatch(r"[0-9a-fA-F]{64}", baseline), label + ".sha256 must contain 64 hex characters")
        strings(item.get("affects_stages"), label + ".affects_stages")
        require(not path.exists() or path.is_file(), label + ".path must reference a file")
        current = sha256(path) if path.is_file() else None
        if current == baseline.lower():
            unchanged += 1
            continue
        changes.append({"path": item["path"], "status": "missing" if current is None else "changed",
                        "previous_sha256": baseline.lower(), "current_sha256": current,
                        "affects_stages": item["affects_stages"]})
        for stage_id in item["affects_stages"]:
            if stage_id not in stages:
                stages.append(stage_id)
    warnings = []
    if direction.get("file") and project_path(root, direction["file"], "session.direction.file").resolve() not in seen:
        warnings.append("The direction file has no evidence hash baseline; its unchanged state cannot be inferred.")
    if any(not change["affects_stages"] for change in changes):
        warnings.append("Changed evidence without an affected-stage mapping needs principal-agent dependency review before resuming.")
    next_step = session.get("next_step")
    if stages:
        next_step = "Recheck only affected stages: " + ", ".join(stages)
    elif changes:
        next_step = "Map changed evidence to affected stages before resuming."
    return {
        "schema_version": 1, "read_only": True, "run_id": session.get("run_id"),
        "evidence_changes": changes, "invalidated_stages": stages,
        "unchanged_evidence_count": unchanged, "blocked": copy.deepcopy(session.get("blocked", [])),
        "direction": copy.deepcopy(direction), "authorization": copy.deepcopy(session["authorization"]),
        "scope": copy.deepcopy(session["scope"]), "warnings": warnings,
        "next_step": next_step,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="Plan structured intent; no writes or skill execution")
    planning.add_argument("--input", required=True, help="Intent JSON file")
    restoring = commands.add_parser("resume", help="Compare session evidence; no writes")
    restoring.add_argument("--session", required=True, help="Recorded session JSON file")
    restoring.add_argument("--project", required=True, help="Project directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            report = plan(read_json(args.input))
        else:
            report = resume(read_json(args.session), args.project)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if args.command == "plan" and report["blocked"] else 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error), "read_only": True}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

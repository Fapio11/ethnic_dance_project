"""Offline unit tests for planner decisions and local evidence comparison.

No upstream execution, browser QA, generation API, or business page mutation.
"""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


DEV = Path(__file__).resolve().parent
SKILL = DEV.parent.parent / "skills" / "creative-web-design"
SCRIPT = SKILL / "scripts" / "workflow.py"
spec = importlib.util.spec_from_file_location("creative_workflow", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def base_intent():
    return {
        "mode": "auto", "task_kind": "frontend-change",
        "direction": {"status": "existing", "reference": "DESIGN.md"},
        "animation": "none",
        "scope": {"allowed_paths": ["src/page.tsx"], "preserve": ["API and navigation"], "target_devices": ["desktop"]},
        "authorization": {"implementation": True, "generation": {
            "status": "not-requested", "service": None, "data_scope": [],
            "max_calls": None, "max_cost": None, "currency": None, "stop_conditions": [],
        }},
        "desired_enhancements": [],
    }


def make_session():
    intent = base_intent()
    return {
        "schema_version": 1, "run_id": "test-local", "task": "resume fixture", "mode": "refine",
        "scope": intent["scope"], "current_stage": "browser-verification",
        "direction": {"status": "user-confirmed", "file": "方向/艺术 方向.md", "confirmation_source": "user turn fixture"},
        "dependencies": [], "authorization": intent["authorization"], "artifacts": [],
        "checks": [], "blocked": [], "next_step": "Review browser evidence", "evidence": [],
    }


class RouteTests(unittest.TestCase):
    def test_deployed_reference_routes_config_is_validated_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory(prefix="路由 配置 ") as directory:
            skill = Path(directory) / "isolated-skill"
            (skill / "scripts").mkdir(parents=True)
            (skill / "references").mkdir()
            deployed = skill / "references" / "routes.json"
            # A valid legacy root file must not conceal an invalid actual config.
            (skill / "routes.json").write_text(json.dumps(workflow.ROUTES), encoding="utf-8")
            deployed.write_text(json.dumps({"schema_version": 1, "modes": ["auto"]}), encoding="utf-8")
            with mock.patch.object(workflow, "__file__", str(skill / "scripts" / "workflow.py")):
                with self.assertRaisesRegex(ValueError, "routes.json"):
                    workflow.plan(base_intent())
                deployed.write_text(json.dumps(workflow.ROUTES), encoding="utf-8")
                self.assertEqual(workflow.plan(base_intent())["effective_mode"], "refine")
                deployed.unlink()
                deployed.mkdir()
                with self.assertRaises(OSError):
                    workflow.plan(base_intent())

    def test_intent_paths_reject_lexical_escape_without_claiming_symlink_validation(self):
        for bad in ("../private.txt", "/tmp/private.txt", "C:\\private.txt", "C:private.txt", "a\\..\\private.txt", "\\\\server\\share\\secret"):
            for field in ("allowed_paths", "reference"):
                with self.subTest(path=bad, field=field):
                    intent = base_intent()
                    if field == "allowed_paths":
                        intent["scope"]["allowed_paths"] = [bad]
                    else:
                        intent["direction"]["reference"] = bad
                    with self.assertRaisesRegex(ValueError, "absolute or traverse"):
                        workflow.plan(intent)
        intent = base_intent()
        intent["scope"]["allowed_paths"] = ["src/页面 空格.tsx", "assets/角色/**"]
        intent["direction"]["reference"] = "方向/艺术 方向.md"
        self.assertEqual(workflow.plan(intent)["scope"], intent["scope"])

    def test_review_task_kind_stays_read_only_with_contradictory_mode(self):
        intent = base_intent()
        intent.update(task_kind="review", mode="build", animation="generate-media", desired_enhancements=["polish"])
        report = workflow.plan(intent)
        self.assertEqual(report["effective_mode"], "review")
        self.assertFalse(any(s["allowed_business_writes"] for s in report["stage_plan"]))
        self.assertEqual(report["generation"]["status"], "not-run")
        self.assertNotIn("media-generation", {s["id"] for s in report["stage_plan"]})

    def test_structured_routing_fixtures(self):
        fixtures = json.loads((DEV / "route_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(fixtures["cases"]), 10)
        for case in fixtures["cases"]:
            with self.subTest(case=case["name"]):
                intent = base_intent()
                intent.update(copy.deepcopy(case["overrides"]))
                report = workflow.plan(intent)
                self.assertEqual(report["effective_mode"], case["mode"])
                self.assertEqual(report["intent"]["authorization"], intent["authorization"])
                self.assertEqual(report["scope"], intent["scope"])
                reads = {s for stage in report["stage_plan"] for s in stage["requested_reads"]}
                stages = {stage["id"] for stage in report["stage_plan"]}
                for name in case.get("reads", []):
                    self.assertIn(name, reads)
                for name in case.get("no_reads", []):
                    self.assertNotIn(name, reads)
                if "stage" in case:
                    self.assertIn(case["stage"], stages)
                if "no_stage" in case:
                    self.assertNotIn(case["no_stage"], stages)
                if "eligible" in case:
                    self.assertEqual(report["eligible"], case["eligible"])
                if "blocked" in case:
                    self.assertEqual(bool(report["blocked"]), case["blocked"])
                if "generation_status" in case:
                    self.assertEqual(report["generation"]["status"], case["generation_status"])
                if "preserve" in case:
                    self.assertEqual(report["scope"]["preserve"], case["preserve"])
                if case.get("no_business_writes"):
                    self.assertFalse(any(s["allowed_business_writes"] for s in report["stage_plan"]))
                self.assertTrue(all(stage["status"] == "planned" for stage in report["stage_plan"]))

    def test_budgets_are_specific_existing_grants_not_automatic_authorization(self):
        intent = base_intent()
        intent.update(mode="motion", animation="generate-media")
        grant = intent["authorization"]["generation"]
        grant.update(status="granted", service="fixture", data_scope=["one approved PNG"], max_calls=1,
                     stop_conditions=["one call maximum"])
        self.assertEqual(workflow.plan(intent)["generation"]["status"], "planned")
        for key, value in (("service", None), ("data_scope", []), ("max_calls", 0), ("stop_conditions", []), ("status", "missing")):
            with self.subTest(missing=key):
                variant = copy.deepcopy(intent)
                variant["authorization"]["generation"][key] = value
                report = workflow.plan(variant)
                self.assertEqual(report["generation"]["status"], "blocked")
                self.assertIn("media specification", report["generation"]["continuation"])
                self.assertNotIn("media-generation", {s["id"] for s in report["stage_plan"]})

    def test_cost_grant_requires_currency_and_valid_numbers(self):
        intent = base_intent()
        intent.update(mode="motion", animation="generate-media")
        grant = intent["authorization"]["generation"]
        grant.update(status="granted", service="fixture", data_scope=["approved data"], max_cost=2,
                     stop_conditions=["budget reached"])
        self.assertEqual(workflow.plan(intent)["generation"]["status"], "blocked")
        grant["currency"] = "USD"
        self.assertEqual(workflow.plan(intent)["generation"]["status"], "planned")
        for field, value in (("max_calls", True), ("max_calls", 1.2), ("max_cost", float("nan")), ("max_cost", float("inf")), ("max_cost", -1)):
            invalid = copy.deepcopy(intent)
            invalid["authorization"]["generation"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                workflow.plan(invalid)

    def test_missing_permission_empty_scope_and_unknown_enhancements(self):
        intent = base_intent()
        intent["authorization"]["implementation"] = False
        report = workflow.plan(intent)
        self.assertTrue(report["blocked"])
        self.assertFalse(any(s["allowed_business_writes"] for s in report["stage_plan"]))
        intent["authorization"]["implementation"] = True
        intent["scope"]["allowed_paths"] = []
        self.assertTrue(workflow.plan(intent)["blocked"])
        intent["desired_enhancements"] = ["imaginary-api"]
        with self.assertRaises(ValueError):
            workflow.plan(intent)

    def test_explore_keeps_isolated_prototypes_even_with_implementation_grant(self):
        intent = base_intent()
        intent.update(mode="explore", animation="native", desired_enhancements=["overdrive"])
        report = workflow.plan(intent)
        self.assertFalse(any(s["allowed_business_writes"] for s in report["stage_plan"]))
        self.assertNotIn("enhancement-overdrive", {s["id"] for s in report["stage_plan"]})
        self.assertTrue(report["intent"]["authorization"]["implementation"])


class ResumeTests(unittest.TestCase):
    def test_changed_direction_missing_asset_and_unchanged_code_are_selective_read_only(self):
        with tempfile.TemporaryDirectory(prefix="创意 网站 ") as directory:
            root = Path(directory)
            paths = ["方向/艺术 方向.md", "素材/角色 帧.png", "src/页面.tsx"]
            session = make_session()
            for name, data, affected in zip(paths, [b"direction", b"frame", b"code"],
                                             [["direction-lock", "browser-verification"], ["motion-integration"], ["implementation-slice"]]):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
                session["evidence"].append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "affects_stages": affected})
            (root / paths[0]).write_text("新方向", encoding="utf-8")
            (root / paths[1]).unlink()
            session_path = root / "session 状态.json"
            session_path.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            report = workflow.resume(session, root)
            self.assertEqual(report["unchanged_evidence_count"], 1)
            self.assertEqual([e["status"] for e in report["evidence_changes"]], ["changed", "missing"])
            self.assertEqual(report["invalidated_stages"], ["direction-lock", "browser-verification", "motion-integration"])
            self.assertNotIn("implementation-slice", report["invalidated_stages"])
            self.assertEqual(report["authorization"], session["authorization"])
            self.assertEqual(report["direction"], session["direction"])
            proc = subprocess.run([sys.executable, str(SCRIPT), "resume", "--session", str(session_path), "--project", str(root)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["invalidated_stages"], report["invalidated_stages"])
            after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_path_traversal_drive_and_symlink_escapes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            session = make_session()
            session["direction"]["file"] = None
            for bad in ("../private.txt", "/tmp/private.txt", "C:\\private.txt", "C:private.txt", "a\\..\\private.txt", "\\\\server\\share\\secret"):
                with self.subTest(path=bad):
                    session["evidence"] = [{"path": bad, "sha256": "0" * 64, "affects_stages": ["direction-lock"]}]
                    with self.assertRaises(ValueError):
                        workflow.resume(session, root)
            private = Path(outside) / "private.txt"
            private.write_text("outside fixture", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(private)
            except OSError:
                self.skipTest("symlink creation is unavailable on this host")
            session["evidence"] = [{"path": "linked.txt", "sha256": "0" * 64, "affects_stages": []}]
            with self.assertRaises(ValueError):
                workflow.resume(session, root)

    def test_no_baseline_is_not_claimed_unchanged_and_invalid_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = make_session()
            report = workflow.resume(session, root)
            self.assertTrue(report["warnings"])
            self.assertEqual(report["next_step"], session["next_step"])
            session["evidence"] = [{"path": "image.png", "sha256": "guess", "affects_stages": []}]
            with self.assertRaises(ValueError):
                workflow.resume(session, root)


class CLITests(unittest.TestCase):
    def test_plan_exit_codes_and_stdout_json(self):
        with tempfile.TemporaryDirectory(prefix="CLI 中文 ") as directory:
            root = Path(directory)
            file = root / "结构 输入.json"
            intent = base_intent()
            file.write_text(json.dumps(intent), encoding="utf-8")
            before = file.read_bytes()
            completed = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(file)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["effective_mode"], "refine")
            self.assertEqual(file.read_bytes(), before)
            intent.update(mode="motion", animation="generate-media")
            file.write_text(json.dumps(intent), encoding="utf-8")
            blocked = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(file)], capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            self.assertTrue(json.loads(blocked.stdout)["blocked"])
            file.write_text("not JSON", encoding="utf-8")
            invalid = subprocess.run([sys.executable, str(SCRIPT), "plan", "--input", str(file)], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 1)
            self.assertTrue(json.loads(invalid.stderr)["read_only"])


if __name__ == "__main__":
    unittest.main()

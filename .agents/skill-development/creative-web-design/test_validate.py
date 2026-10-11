"""Offline negative tests against disposable copies of the real package.

No external services, package installation or business page writes. The mocked
official branch tests report separation only, not official compatibility.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PACKAGE = Path(__file__).resolve().parents[2] / "skills" / "creative-web-design"
sys.path.insert(0, str(PACKAGE / "scripts"))
SPEC = importlib.util.spec_from_file_location("creative_validate", PACKAGE / "scripts" / "validate.py")
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="creative skill 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "项目 包" / "creative-web-design"
        shutil.copytree(PACKAGE, self.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def package_errors(self):
        return VALIDATE.validate_package(self.package)["errors"]

    def mutate_json(self, relative, mutate):
        path = self.package / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def session(self, mutate=None):
        path = self.package / "assets/templates/session.json"
        if mutate:
            self.mutate_json("assets/templates/session.json", mutate)
        return VALIDATE.validate_session(path)

    def test_real_package_and_chinese_space_path(self):
        self.assertEqual(self.package_errors(), [])

    def test_missing_required_file(self):
        (self.package / "references/quality-gates.md").unlink()
        self.assertTrue(any("missing required file references/quality-gates.md" in e for e in self.package_errors()))

    def test_wrong_skill_name(self):
        path = self.package / "SKILL.md"
        content = path.read_text(encoding="utf-8").replace("name: creative-web-design", "name: unrelated-skill", 1)
        path.write_text(content, encoding="utf-8")
        self.assertTrue(any("name must be creative-web-design" in e for e in self.package_errors()))

    def test_empty_description(self):
        path = self.package / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        start = content.index("description:")
        end = content.index("\n", start)
        content = content[:start] + 'description: ""' + content[end:]
        path.write_text(content, encoding="utf-8")
        self.assertTrue(any("description" in e and "nonempty" in e for e in self.package_errors()))

    def test_fake_mcp_dependency(self):
        path = self.package / "agents/openai.yaml"
        with path.open("a", encoding="utf-8") as out:
            out.write('\ndependencies:\n  tools: "design-taste-frontend"\n')
        self.assertTrue(any("child skills are not MCP" in e for e in self.package_errors()))

    def test_missing_explicit_prompt(self):
        path = self.package / "agents/openai.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("$creative-web-design", "$wrong-skill"), encoding="utf-8")
        self.assertTrue(any("default_prompt must include literal" in e for e in self.package_errors()))

    def test_broken_reference_and_anchor(self):
        path = self.package / "SKILL.md"
        with path.open("a", encoding="utf-8") as out:
            out.write("\n[missing](references/absent.md)\n[anchor](references/workflow.md#never-an-existing-heading)\n")
        errors = self.package_errors()
        self.assertTrue(any("missing internal reference" in e for e in errors))
        self.assertTrue(any("missing anchor" in e for e in errors))

    def test_reference_cannot_escape_package(self):
        outside = self.package.parent / "outside.md"
        outside.write_text("present, but outside", encoding="utf-8")
        with (self.package / "SKILL.md").open("a", encoding="utf-8") as out:
            out.write("\n[outside](../outside.md)\n")
        self.assertTrue(any("escapes skill" in e for e in self.package_errors()))

    def test_internal_parent_reference_allowed(self):
        with (self.package / "references/workflow.md").open("a", encoding="utf-8") as out:
            out.write("\n[Entry](../SKILL.md)\n")
        self.assertEqual(self.package_errors(), [])

    def test_fenced_example_is_not_a_link(self):
        with (self.package / "SKILL.md").open("a", encoding="utf-8") as out:
            out.write("\n```python\nprint('[Runtime variable](missing-runtime-file.md)')\n```\n")
        self.assertEqual(self.package_errors(), [])

    def test_route_mode_and_status_contract(self):
        self.mutate_json("references/routes.json", lambda x: x["modes"].append("magic"))
        self.mutate_json("references/routes.json", lambda x: x["stage_statuses"].append("called"))
        errors = self.package_errors()
        self.assertTrue(any("routes.modes" in e for e in errors))
        self.assertTrue(any("routes.stage_statuses" in e for e in errors))

    def test_manifest_forbids_local_paths(self):
        self.mutate_json("references/upstreams.json", lambda x: x["upstreams"][0].update(source_path="/Users/example/.codex/skills/taste/SKILL.md"))
        self.assertTrue(any("local absolute filesystem paths" in e for e in self.package_errors()))

    def test_windows_manifest_absolute_path(self):
        self.mutate_json("references/upstreams.json", lambda x: x["upstreams"][0].update(source_path="C:\\Users\\Example\\skills\\SKILL.md"))
        self.assertTrue(any("local absolute filesystem paths" in e for e in self.package_errors()))

    def test_manifest_short_sha_rejected(self):
        self.mutate_json("references/upstreams.json", lambda x: x["upstreams"][0].update(commit="123abcd"))
        self.assertTrue(any("full 40-character SHA" in e for e in self.package_errors()))

    def test_manifest_invalid_name_type_does_not_crash(self):
        self.mutate_json("references/upstreams.json", lambda x: x["upstreams"][0].update(logical_name={"invalid": True}))
        self.assertTrue(any("logical_name must be string" in e for e in self.package_errors()))

    def test_verified_without_evidence_rejected(self):
        errors = self.session(lambda x: x["checks"].append({"id": "browser", "status": "verified", "evidence": []}))
        self.assertTrue(any("verified status requires evidence" in e for e in errors))

    def test_verified_with_boolean_evidence_rejected(self):
        errors = self.session(lambda x: x["checks"].append({"id": "browser", "status": "verified", "evidence": True}))
        self.assertTrue(any("verified status requires evidence" in e for e in errors))

    def test_invalid_status_rejected(self):
        errors = self.session(lambda x: x["checks"].append({"id": "browser", "status": "called"}))
        self.assertTrue(any(".status is invalid" in e for e in errors))

    def test_user_direction_requires_source(self):
        errors = self.session(lambda x: x["direction"].update(status="user-confirmed", file="art-direction.md"))
        self.assertTrue(any("requires file and user confirmation source" in e for e in errors))

    def test_generation_grant_requires_budget_and_stop(self):
        errors = self.session(lambda x: x["authorization"]["generation"].update(status="granted", service="example-service", data_scope=["character.png"]))
        self.assertTrue(any("stop conditions" in e for e in errors))
        self.assertTrue(any("positive call or cost budget" in e for e in errors))

    def test_zero_generation_budget_does_not_grant_spending(self):
        errors = self.session(lambda x: x["authorization"]["generation"].update(status="granted", service="example-service", data_scope=["character.png"], max_calls=0, max_cost=0, stop_conditions=["Stop after one sample"]))
        self.assertTrue(any("positive call or cost budget" in e for e in errors))

    def test_positive_call_budget_is_valid(self):
        errors = self.session(lambda x: x["authorization"]["generation"].update(status="granted", service="example-service", data_scope=["character.png"], max_calls=1, stop_conditions=["Stop after one sample"]))
        self.assertEqual(errors, [])

    def test_credentials_are_not_recordable(self):
        errors = self.session(lambda x: x["authorization"]["generation"].update(api_key="fixture value, not a key"))
        self.assertTrue(any("forbidden credential field api_key" in e for e in errors))

    def test_review_cannot_grant_business_writes(self):
        def mutate(x):
            x["mode"] = "review"
            x["authorization"]["implementation"] = True
        self.assertTrue(any("explore/review" in e for e in self.session(mutate)))

    def test_implementation_requires_scoped_paths(self):
        def mutate(x):
            x["mode"] = "build"
            x["authorization"]["implementation"] = True
            x["direction"].update(status="user-confirmed", file="art-direction.md", confirmation_source="User message approving the direction")
        self.assertTrue(any("explicit allowed_paths scope" in e for e in self.session(mutate)))

    def test_completion_cannot_hide_blocker(self):
        def mutate(x):
            x["current_stage"] = "complete"
            x["blocked"] = [{"stage": "media-generation", "reason": "No generation authorization"}]
        self.assertTrue(any("cannot claim completion" in e for e in self.session(mutate)))

    def test_artifact_path_cannot_escape(self):
        errors = self.session(lambda x: x["artifacts"].append({"path": "../business-file", "status": "planned"}))
        self.assertTrue(any("safe relative path" in e for e in errors))

    def test_bad_json_reports_error(self):
        path = self.package / "assets/templates/session.json"
        path.write_text("{broken json", encoding="utf-8")
        self.assertTrue(VALIDATE.validate_session(path))

    def test_cli_default_never_runs_official_script(self):
        process = subprocess.run([sys.executable, str(self.package / "scripts/validate.py"), str(self.package)], capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["custom"]["status"], "passed")
        self.assertEqual(report["official"]["status"], "not-run")
        self.assertIn("Custom package", report["scope"])

    def test_missing_official_validator_does_not_install(self):
        report = VALIDATE.official_check(self.package / "missing-validator.py", self.package)
        self.assertEqual(report["status"], "not-run")

    def test_missing_pyyaml_does_not_execute_script(self):
        script = self.package / "reviewed-test-validator.py"
        marker = self.package / "must-not-exist"
        script.write_text("from pathlib import Path\nPath({!r}).touch()\n".format(str(marker)), encoding="utf-8")
        with mock.patch.object(VALIDATE.importlib.util, "find_spec", return_value=None):
            report = VALIDATE.official_check(script, self.package)
        self.assertEqual(report["status"], "not-run")
        self.assertIn("PyYAML", report["reason"])
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

"""Offline discovery/error/provenance tests. No user files or service calls."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "skills" / "creative-web-design" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import doctor
from skill_utils import parse_frontmatter, read_frontmatter


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="creative doctor 中文 ")
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "项目 工作区"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.home = self.base / "本机 用户"
        self.home.mkdir()
        self.skills = self.project / ".agents" / "skills"
        self.skills.mkdir(parents=True)
        self.manifest = self.base / "清单 文件.json"
        self.manifest.write_text('{"schema_version":1,"upstreams":[]}', encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def skill(self, folder, actual=None, version=None, root=None, text=None):
        path = (root or self.skills) / folder / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            text = "---\nname: %s\ndescription: Creative fixture used only in isolated tests\n" % (actual or folder)
            if version is not None:
                text += "metadata:\n  version: '%s'\n" % version
            text += "---\n\n# Fixture\n"
        path.write_text(text, encoding="utf-8")
        return path

    def args(self, require=None, media=False, skill_root=None):
        return argparse.Namespace(project=str(self.project), skill_root=skill_root or [],
                                  require=require, manifest=str(self.manifest), media=media, shareable=False)

    def run_doctor(self, args=None):
        args = args or self.args()
        roots = doctor.search_roots(self.project, args.skill_root, environment={}, home=self.home)
        with mock.patch.object(doctor, "search_roots", return_value=roots):
            return doctor.run(args)

    def dep(self, result, logical):
        return next(item for item in result["dependencies"] if item["logical_name"] == logical)

    def install_all(self):
        for actual in doctor.EXPECTED.values():
            self.skill(actual)

    def test_chinese_spaces_and_actual_frontmatter_names_not_folder_guesses(self):
        self.skill("任意名字", actual="design-taste-frontend")
        self.skill("其它目录", actual="impeccable", version="4.5.2")
        self.skill("oil-motion")
        result, code = self.run_doctor()
        self.assertEqual(0, code)
        self.assertEqual("4.5.2", self.dep(result, "impeccable")["candidates"][0]["actual_version"])
        self.assertIn("项目 工作区", self.dep(result, "taste")["candidates"][0]["entry_path"])

    def test_missing_required_exits_two_but_phase_only_accepts_missing_others(self):
        self.skill("design-taste-frontend")
        result, code = self.run_doctor()
        self.assertEqual(2, code)
        self.assertEqual(["impeccable", "oil-motion"], result["summary"]["unavailable_requirements"])
        phase, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(0, code)
        self.assertEqual("missing", self.dep(phase, "oil-motion")["status"])

    def test_equal_hash_duplicate_installs_are_ambiguous(self):
        first = self.skill("design-taste-frontend")
        other_root = self.base / "另一安装 skills"
        other_root.mkdir()
        second = self.skill("alternate", actual="design-taste-frontend", root=other_root)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        result, code = self.run_doctor(self.args(require=["taste"], skill_root=[str(other_root)]))
        self.assertEqual(2, code)
        self.assertEqual("ambiguous", self.dep(result, "taste")["status"])
        self.assertEqual(2, len(self.dep(result, "taste")["candidates"]))

    def test_symlink_same_canonical_entry_deduplicates(self):
        original = self.skill("design-taste-frontend")
        alias_root = self.base / "链接集合"
        alias_root.mkdir()
        try:
            (alias_root / "same").symlink_to(original.parent, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Symlinks unavailable on this host: %s" % type(exc).__name__)
        result, code = self.run_doctor(self.args(require=["taste"], skill_root=[str(alias_root), str(original.parent)]))
        self.assertEqual(0, code)
        self.assertEqual(1, len(self.dep(result, "taste")["candidates"]))

    def test_malformed_candidate_cannot_be_reported_as_available(self):
        self.skill("design-taste-frontend", text="name: design-taste-frontend\n")
        result, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(1, code)
        self.assertTrue(any(item["code"] == "frontmatter-invalid" for item in result["errors"]))
        self.assertEqual("missing", self.dep(result, "taste")["status"])

    def test_unreadable_entry_reports_read_error(self):
        entry = self.skill("design-taste-frontend")
        with mock.patch.object(doctor, "read_frontmatter", side_effect=PermissionError(13, "denied", str(entry))):
            result, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(1, code)
        self.assertEqual("entry-read-error", result["errors"][0]["code"])
        self.assertNotIn(str(entry), result["errors"][0]["message"])

    def test_mismatched_conventional_folder_name_is_explicit(self):
        self.skill("design-taste-frontend", actual="other-skill")
        result, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(1, code)
        self.assertTrue(any(item["code"] == "name-mismatch" for item in result["errors"]))

    def test_unrelated_known_malformed_entry_warns_without_identifying_candidate(self):
        self.skill("impeccable")
        self.skill("oil-motion", text="---\nname: oil-motion\ndescription: [invalid, mapping]\n---\n")
        result, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(0, code)
        self.assertEqual([], result["errors"])
        self.assertEqual("available", self.dep(result, "impeccable")["status"])
        self.assertEqual("missing", self.dep(result, "oil-motion")["status"])
        self.assertEqual([], self.dep(result, "oil-motion")["candidates"])
        self.assertEqual("frontmatter-invalid", result["warnings"][0]["code"])
        self.assertEqual(["oil-motion"], result["warnings"][0]["affected_dependencies"])
        self.assertEqual("not-required-for-this-phase", result["warnings"][0]["reason"])
        required, code = self.run_doctor(self.args(require=["oil-motion"]))
        self.assertEqual(1, code)
        self.assertEqual([], required["warnings"])
        default, code = self.run_doctor()
        self.assertEqual(1, code)
        self.assertTrue(default["errors"])

    def test_unrelated_known_name_conflict_warns_but_required_names_stay_fatal(self):
        self.skill("impeccable")
        self.skill("oil-motion", actual="design-taste-frontend")
        unrelated, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(0, code)
        self.assertEqual("name-mismatch", unrelated["warnings"][0]["code"])
        self.assertEqual(["oil-motion", "taste"], unrelated["warnings"][0]["affected_dependencies"])
        self.assertEqual("available", self.dep(unrelated, "taste")["status"])
        for requirement in ("oil-motion", "taste"):
            with self.subTest(requirement=requirement):
                result, code = self.run_doctor(self.args(require=[requirement]))
                self.assertEqual(1, code)
                self.assertTrue(any(item["code"] == "name-mismatch" for item in result["errors"]))

    def test_required_declared_name_in_unrelated_folder_cannot_be_ignored(self):
        self.skill("impeccable")
        self.skill("oil-motion", actual="impeccable")
        result, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(1, code)
        self.assertEqual("ambiguous", self.dep(result, "impeccable")["status"])
        self.assertEqual(["impeccable", "oil-motion"], result["errors"][0]["affected_dependencies"])
        self.assertEqual([], result["warnings"])
        self.skill("oil-motion", text="---\nname: 'impeccable'\ndescription: [invalid]\n---\n")
        malformed, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(1, code)
        self.assertEqual("frontmatter-invalid", malformed["errors"][0]["code"])

    def test_unknown_and_conflicting_declarations_are_conservatively_fatal(self):
        self.skill("impeccable")
        cases = [
            "---\nname: unknown-skill\ndescription: Valid description\n---\n",
            "---\nname: unknown-skill\ndescription: [invalid]\n---\n",
            "---\nname: oil-motion\nname: impeccable\ndescription: Valid description\n---\n",
            "---\nname: oil-motion\nname: oil-motion\ndescription: Valid description\n---\n",
            "---\ndescription: [invalid]\n---\n",
            "name: oil-motion\n",
        ]
        for content in cases:
            with self.subTest(content=content):
                self.skill("oil-motion", text=content)
                result, code = self.run_doctor(self.args(require=["impeccable"]))
                self.assertEqual(1, code)
                self.assertEqual([], result["warnings"])
                self.assertTrue(result["errors"])

    def test_unknown_directory_parse_and_known_directory_read_errors_stay_fatal(self):
        self.skill("impeccable")
        self.skill("unrecognized-folder", text="---\nname: oil-motion\ndescription: [invalid]\n---\n")
        result, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(1, code)
        self.assertEqual([], result["warnings"])
        (self.skills / "unrecognized-folder" / "SKILL.md").unlink()
        entry = self.skill("oil-motion")
        original = doctor.read_frontmatter

        def selective_read(path):
            if path == entry:
                raise PermissionError(13, "denied", str(entry))
            return original(path)

        with mock.patch.object(doctor, "read_frontmatter", side_effect=selective_read):
            unreadable, code = self.run_doctor(self.args(require=["impeccable"]))
        self.assertEqual(1, code)
        self.assertEqual("entry-read-error", unreadable["errors"][0]["code"])
        self.assertEqual([], unreadable["warnings"])

    def test_media_added_requirement_does_not_downgrade_broken_oil(self):
        self.skill("impeccable")
        self.skill("oil-motion", text="---\nname: oil-motion\ndescription: [invalid]\n---\n")
        result, code = self.run_doctor(self.args(require=["impeccable"], media=True))
        self.assertEqual(1, code)
        self.assertIn("oil-motion", result["requirements"])
        self.assertEqual([], result["warnings"])
        self.assertEqual("unavailable", result["media"]["status"])

    def test_unknown_version_and_provenance_require_matching_hash(self):
        entry = self.skill("design-taste-frontend")
        source = {"logical_name": "taste", "expected_name": "design-taste-frontend",
                  "repository": "https://example.test/taste", "source_path": "SKILL.md", "checked_on": "2026-10-10",
                  "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest(), "version": "v2",
                  "commit": "a" * 40, "upstream_entry_sha256": None, "local_modification": None}
        self.manifest.write_text(json.dumps({"schema_version": 1, "upstreams": [source]}), encoding="utf-8")
        matched, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(0, code)
        current = self.dep(matched, "taste")["candidates"][0]
        self.assertEqual("unknown", current["actual_version"])
        self.assertEqual("v2", current["provenance"]["source_version"])
        self.assertEqual("a" * 40, current["provenance"]["source_commit"])
        entry.write_text(entry.read_text(encoding="utf-8") + "Changed body\n", encoding="utf-8")
        drifted, code = self.run_doctor(self.args(require=["taste"]))
        changed = self.dep(drifted, "taste")["candidates"][0]
        self.assertEqual(0, code)  # Available entry may drift; drift is separate evidence.
        self.assertEqual("changed", changed["drift"])
        self.assertIsNone(changed["provenance"]["source_version"])
        self.assertIsNone(changed["provenance"]["source_commit"])

    def test_discovery_is_independent_of_absent_manifest(self):
        self.skill("design-taste-frontend")
        roots = doctor.search_roots(self.project, [], environment={}, home=self.home)
        dependencies, errors = doctor.discover(roots)
        self.assertEqual([], errors)
        self.assertEqual("available", next(item for item in dependencies if item["logical_name"] == "taste")["status"])

    def test_bad_manifest_is_error_not_silent_provenance(self):
        self.skill("design-taste-frontend")
        self.manifest.write_text("{}", encoding="utf-8")
        result, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(1, code)
        self.assertTrue(any(item["code"] == "manifest-invalid" for item in result["errors"]))

    def test_git_boundary_custom_codex_home_and_excluded_recursion(self):
        nested = self.project / "子目录" / "深一层"
        nested.mkdir(parents=True)
        roots = doctor.search_roots(nested, [], environment={"CODEX_HOME": str(self.base / "Configured Codex")}, home=self.home)
        paths = [Path(item["path"]) for item in roots]
        self.assertIn(self.project / ".agents" / "skills", paths)
        self.assertNotIn(self.base / ".agents" / "skills", paths)
        self.assertIn(self.base / "Configured Codex" / "skills", paths)
        self.assertNotIn(self.home / ".codex" / "skills", paths)
        self.skill("nested", actual="design-taste-frontend", root=self.skills / "node_modules")
        self.skill("deep", actual="design-taste-frontend", root=self.skills / "ordinary" / "nested")
        result, code = self.run_doctor(self.args(require=["taste"]))
        self.assertEqual(2, code)
        self.assertEqual("missing", self.dep(result, "taste")["status"])

    def test_explicit_missing_root_and_bad_project_are_input_errors(self):
        result, code = self.run_doctor(self.args(require=["taste"], skill_root=[str(self.base / "missing")]))
        self.assertEqual(1, code)
        args = self.args()
        args.project = str(self.base / "absent project")
        result, code = self.run_doctor(args)
        self.assertEqual(1, code)

    def test_scan_bound_and_unknown_requirement_are_errors(self):
        with mock.patch.object(doctor, "MAX_CHILDREN", 2):
            self.install_all()
            result, code = self.run_doctor()
        self.assertEqual(1, code)
        self.assertTrue(any(item["code"] == "scan-bound" for item in result["errors"]))
        result, code = self.run_doctor(self.args(require=["made-up"]))
        self.assertEqual(1, code)

    def test_media_has_no_unconditional_dependency_or_process_call(self):
        self.install_all()
        with mock.patch.object(doctor.subprocess, "run", side_effect=AssertionError("No media command should run")):
            result, code = self.run_doctor()
        self.assertEqual(0, code)
        self.assertEqual("not-requested", result["media"]["status"])

    def test_media_only_fixed_version_probes_and_no_credentials(self):
        entry = self.skill("oil-motion")
        venv = entry.parent / ".venv"
        for name in ("python", "ffmpeg", "ffprobe"):
            path = venv / "bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        package_root = venv / "lib" / "python3.11" / "site-packages"
        metadata = package_root / "pillow-12.3.0.dist-info" / "METADATA"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("Name: Pillow\nVersion: 12.3.0\n", encoding="utf-8")
        (package_root / "PIL").mkdir()
        (package_root / "PIL" / "__init__.py").write_text("raise Exception('must not import')", encoding="utf-8")
        (entry.parent / "LOCAL-RUNTIME.md").write_text("Do not execute this file", encoding="utf-8")
        commands = []

        def probe(command, **kwargs):
            commands.append(command)
            name = Path(command[0]).name
            output = "Python 3.11.16" if name == "python" else name + " version 8.0"
            return subprocess.CompletedProcess(command, 0, output, "")

        with mock.patch.object(doctor.subprocess, "run", side_effect=probe):
            result, code = self.run_doctor(self.args(require=["oil-motion"], media=True))
        self.assertEqual(0, code)
        self.assertEqual("available", result["media"]["status"])
        self.assertEqual([["-I", "--version"], ["-version"], ["-version"]], [item[1:] for item in commands])
        self.assertTrue(result["media"]["local_runtime"]["note_present"])
        self.assertEqual("metadata-only; import not executed", result["media"]["pillow"]["verification"])

    def test_media_unavailable_is_exit_two_and_requires_oil(self):
        self.skill("design-taste-frontend")
        result, code = self.run_doctor(self.args(require=["taste"], media=True))
        self.assertEqual(2, code)
        self.assertIn("oil-motion", result["requirements"])
        self.assertEqual("unavailable", result["media"]["status"])

    def test_shareable_main_redacts_local_paths_and_is_valid_json(self):
        self.skill("design-taste-frontend")
        roots = doctor.search_roots(self.project, [], environment={}, home=self.home)
        capture = io.StringIO()
        with mock.patch.object(doctor, "search_roots", return_value=roots), contextlib.redirect_stdout(capture):
            code = doctor.main(["--project", str(self.project), "--require", "design-taste-frontend", "--manifest", str(self.manifest), "--shareable"])
        output = capture.getvalue()
        result = json.loads(output)
        self.assertEqual(0, code)
        self.assertNotIn(str(self.base), output)
        self.assertEqual("<local-path>", self.dep(result, "taste")["candidates"][0]["entry_path"])
        self.assertEqual("<local-path>", doctor.redact_paths("C:\\Users\\someone\\skills\\SKILL.md"))

    def test_cli_invalid_arguments_are_json_input_error_exit_one(self):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = doctor.main(["--project"])
        self.assertEqual(1, code)
        self.assertEqual("invalid-arguments", json.loads(capture.getvalue())["errors"][0]["code"])

    def test_program_keeps_virtual_environment_symlink_path(self):
        base_python = self.base / "base-python"
        base_python.write_text("", encoding="utf-8")
        selected = self.base / ".venv" / "bin" / "python"
        selected.parent.mkdir(parents=True)
        try:
            selected.symlink_to(base_python)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Symlinks unavailable on this host: %s" % type(exc).__name__)
        self.assertEqual(str(selected), doctor._program([selected], "python3"))


class FrontmatterTests(unittest.TestCase):
    def test_plain_quoted_blocks_and_metadata(self):
        data = parse_frontmatter("---\nname: 'valid-name'\ndescription: >-\n  First line\n  第二行\nmetadata:\n  version: 4.5.2\n  short-description: \"A # literal\"\n---\nBody\n")
        self.assertEqual("First line 第二行", data["description"])
        self.assertEqual("4.5.2", data["metadata"]["version"])
        self.assertEqual("A # literal", data["metadata"]["short-description"])
        self.assertEqual("it's valid", parse_frontmatter("---\nname: valid-name\ndescription: 'it''s valid'\n---\n")["description"])

    def test_malformed_and_unsupported_yaml_fail_explicitly(self):
        cases = [
            "name: valid-name\ndescription: x", "---\nname: valid-name\ndescription: x",
            "---\nname: valid-name\n---", "---\nname: valid-name\ndescription: null\n---",
            "---\nname: valid-name\ndescription: [a,b]\n---", "---\nname: valid-name\ndescription: &anchor word\n---",
            "---\nname: valid-name\nname: duplicate\ndescription: x\n---",
            "---\nname: valid-name\ndescription: x\nmetadata:\n  version: 1.0\n---",
            "---\nname: valid-name\ndescription: x\nmetadata:\n  nested:\n    version: string\n---",
            "---\nname: valid-name\ndescription: 'unclosed\n---", "---\nname: valid-name\ndescription: a: b\n---",
            "---\nname: valid-name\ndescription: \"bad\"#unspaced\n---",
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_frontmatter(text)


if __name__ == "__main__":
    unittest.main()

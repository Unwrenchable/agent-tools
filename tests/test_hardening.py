from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Allow importing from tools/ without installing it
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from harden_repos import (
    _KNOWN_ECOSYSTEMS,
    _POLICY_DEFAULTS,
    _dependabot_entry,
    build_codeowners,
    build_dependabot_yml,
    build_license_text,
    build_pr_template,
    build_security_md,
    build_security_workflow,
    detect_ecosystems,
    load_policy,
    update_readme_with_license,
    write_hardening_files,
)


# ── load_policy ────────────────────────────────────────────────────────────────


class TestLoadPolicy:
    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        policy = load_policy(tmp_path / "nonexistent.json")
        assert policy["license_mode"] == "non-commercial"
        assert policy["approvals_required"] == 1
        assert policy["dependabot_schedule"] == "weekly"

    def test_merges_overrides(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(
            json.dumps({"license_mode": "dual", "approvals_required": 2}),
            encoding="utf-8",
        )
        policy = load_policy(policy_file)
        assert policy["license_mode"] == "dual"
        assert policy["approvals_required"] == 2
        # defaults still present
        assert policy["dependabot_schedule"] == "weekly"

    def test_deep_merges_branch_protection(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(
            json.dumps({"branch_protection": {"approvals_required": 3}}),
            encoding="utf-8",
        )
        policy = load_policy(policy_file)
        bp = policy["branch_protection"]
        assert bp["approvals_required"] == 3
        # other branch_protection defaults preserved
        assert bp["dismiss_stale_reviews"] is True

    def test_contact_field_stored(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(
            json.dumps({"license_contact": "me@example.com"}),
            encoding="utf-8",
        )
        policy = load_policy(policy_file)
        assert policy["license_contact"] == "me@example.com"


# ── detect_ecosystems ──────────────────────────────────────────────────────────


class TestDetectEcosystems:
    def test_detects_npm(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        assert "npm" in detect_ecosystems(tmp_path)

    def test_detects_pip_from_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").touch()
        assert "pip" in detect_ecosystems(tmp_path)

    def test_detects_pip_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        assert "pip" in detect_ecosystems(tmp_path)

    def test_detects_cargo(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert "cargo" in detect_ecosystems(tmp_path)

    def test_detects_gomod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert "gomod" in detect_ecosystems(tmp_path)

    def test_detects_github_actions(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        assert "github-actions" in detect_ecosystems(tmp_path)

    def test_detects_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        (tmp_path / "requirements.txt").touch()
        ecosystems = detect_ecosystems(tmp_path)
        assert "npm" in ecosystems
        assert "pip" in ecosystems

    def test_no_duplicates(self, tmp_path: Path) -> None:
        # Pipfile and requirements.txt both map to pip
        (tmp_path / "Pipfile").touch()
        (tmp_path / "requirements.txt").touch()
        ecosystems = detect_ecosystems(tmp_path)
        assert ecosystems.count("pip") == 1

    def test_empty_repo(self, tmp_path: Path) -> None:
        # No files → no ecosystems detected
        assert detect_ecosystems(tmp_path) == []


# ── build_security_md ─────────────────────────────────────────────────────────


class TestBuildSecurityMd:
    def test_contains_reporting_instructions(self) -> None:
        md = build_security_md()
        assert "private" in md.lower() or "privately" in md.lower()
        assert "vulnerability" in md.lower()

    def test_contains_supported_versions(self) -> None:
        md = build_security_md()
        assert "Supported Versions" in md

    def test_contains_disclosure_section(self) -> None:
        md = build_security_md()
        assert "Disclosure" in md

    def test_no_direct_public_issue(self) -> None:
        md = build_security_md()
        assert "do not open a public issue" in md.lower()


# ── build_codeowners ──────────────────────────────────────────────────────────


class TestBuildCodeowners:
    def test_includes_owner_handle(self) -> None:
        content = build_codeowners("Unwrenchable", [])
        assert "@Unwrenchable" in content

    def test_prepends_at_sign(self) -> None:
        content = build_codeowners("myorg", [])
        assert "@myorg" in content

    def test_strips_existing_at_sign(self) -> None:
        content = build_codeowners("@myorg", [])
        assert "@@myorg" not in content
        assert "@myorg" in content

    def test_includes_workflows_path(self) -> None:
        content = build_codeowners("owner", [])
        assert ".github/workflows/**" in content

    def test_includes_custom_paths(self) -> None:
        content = build_codeowners("owner", ["Cargo.lock", "go.sum"])
        assert "Cargo.lock" in content
        assert "go.sum" in content


# ── _dependabot_entry ─────────────────────────────────────────────────────────


class TestDependabotEntry:
    def test_github_actions_has_no_pr_limit(self) -> None:
        entry = _dependabot_entry("github-actions", "weekly")
        assert "open-pull-requests-limit" not in entry

    def test_other_ecosystems_have_pr_limit(self) -> None:
        for eco in ("npm", "pip", "cargo", "gomod"):
            assert "open-pull-requests-limit: 10" in _dependabot_entry(eco, "weekly")

    def test_known_ecosystems_set(self) -> None:
        assert "npm" in _KNOWN_ECOSYSTEMS
        assert "github-actions" in _KNOWN_ECOSYSTEMS
        assert "unknown-eco" not in _KNOWN_ECOSYSTEMS


# ── build_dependabot_yml ──────────────────────────────────────────────────────


class TestBuildDependabotYml:
    def test_valid_yaml_header(self) -> None:
        yml = build_dependabot_yml(["npm"], "weekly")
        assert yml.startswith("version: 2")
        assert "updates:" in yml

    def test_npm_ecosystem(self) -> None:
        yml = build_dependabot_yml(["npm"], "weekly")
        assert 'package-ecosystem: "npm"' in yml

    def test_github_actions_ecosystem(self) -> None:
        yml = build_dependabot_yml(["github-actions"], "weekly")
        assert 'package-ecosystem: "github-actions"' in yml

    def test_schedule_interval(self) -> None:
        yml = build_dependabot_yml(["pip"], "monthly")
        assert 'interval: "monthly"' in yml

    def test_multiple_ecosystems(self) -> None:
        yml = build_dependabot_yml(["npm", "pip", "github-actions"], "weekly")
        assert 'package-ecosystem: "npm"' in yml
        assert 'package-ecosystem: "pip"' in yml
        assert 'package-ecosystem: "github-actions"' in yml

    def test_fallback_when_empty(self) -> None:
        yml = build_dependabot_yml([], "weekly")
        assert 'package-ecosystem: "github-actions"' in yml

    def test_invalid_schedule_defaults_to_weekly(self) -> None:
        yml = build_dependabot_yml(["npm"], "quarterly")
        assert 'interval: "weekly"' in yml


# ── build_pr_template ─────────────────────────────────────────────────────────


class TestBuildPrTemplate:
    def test_contains_security_checklist(self) -> None:
        md = build_pr_template()
        assert "Security Checklist" in md

    def test_contains_dependency_check(self) -> None:
        md = build_pr_template()
        assert "Dependency" in md or "dependency" in md

    def test_contains_secrets_check(self) -> None:
        md = build_pr_template()
        assert "Secret" in md or "secret" in md

    def test_contains_workflow_check(self) -> None:
        md = build_pr_template()
        assert "workflow" in md.lower() or "Workflow" in md

    def test_contains_tests_check(self) -> None:
        md = build_pr_template()
        assert "test" in md.lower()


# ── build_license_text ────────────────────────────────────────────────────────


class TestBuildLicenseText:
    def test_noncommercial_mode(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "non-commercial"}
        text = build_license_text(policy, 2025, "Unwrenchable")
        assert "Non-Commercial" in text
        assert "2025" in text
        assert "Unwrenchable" in text

    def test_dual_mode_header(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "dual", "license_contact": "me@example.com"}
        text = build_license_text(policy, 2025, "Unwrenchable")
        assert "dual" in text.lower() or "Dual" in text
        assert "me@example.com" in text

    def test_contact_clause_in_nc(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "non-commercial", "license_contact": "sales@example.com"}
        text = build_license_text(policy, 2025, "Owner")
        assert "sales@example.com" in text

    def test_no_contact_clause_when_empty(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "non-commercial", "license_contact": ""}
        text = build_license_text(policy, 2025, "Owner")
        # Neither a mailto nor a contact address should appear when contact is empty
        assert "contact:" not in text.lower()
        assert "@" not in text  # no email address


# ── update_readme_with_license ────────────────────────────────────────────────


class TestUpdateReadmeWithLicense:
    def test_appends_to_readme_without_section(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "non-commercial"}
        result = update_readme_with_license("# My Repo\n\nSome content.\n", policy, "Unwrenchable")
        assert "## License" in result
        assert "non-commercial" in result.lower()

    def test_replaces_existing_license_section(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "dual"}
        original = "# My Repo\n\n## License\n\nOld license text.\n\n## Other\n\nContent.\n"
        result = update_readme_with_license(original, policy, "Unwrenchable")
        assert "Old license text." not in result
        assert "dual" in result.lower() or "Dual" in result

    def test_preserves_other_sections(self) -> None:
        policy = {**_POLICY_DEFAULTS}
        original = "# My Repo\n\n## Usage\n\nDo stuff.\n"
        result = update_readme_with_license(original, policy, "owner")
        assert "## Usage" in result
        assert "Do stuff." in result

    def test_owner_handle_in_readme(self) -> None:
        policy = {**_POLICY_DEFAULTS, "license_mode": "non-commercial"}
        result = update_readme_with_license("# Repo\n", policy, "myowner")
        assert "myowner" in result


# ── write_hardening_files (integration) ───────────────────────────────────────


class TestWriteHardeningFiles:
    def test_creates_expected_files(self, tmp_path: Path) -> None:
        policy = load_policy(None)
        write_hardening_files(tmp_path, "testowner", policy)

        assert (tmp_path / "SECURITY.md").exists()
        assert (tmp_path / ".github" / "CODEOWNERS").exists()
        assert (tmp_path / ".github" / "dependabot.yml").exists()
        assert (tmp_path / ".github" / "pull_request_template.md").exists()
        assert (tmp_path / ".github" / "workflows" / "security.yml").exists()
        assert (tmp_path / "LICENSE").exists()

    def test_creates_readme_when_missing(self, tmp_path: Path) -> None:
        policy = load_policy(None)
        write_hardening_files(tmp_path, "testowner", policy)
        assert (tmp_path / "README.md").exists()
        readme = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "## License" in readme

    def test_updates_existing_readme(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# My Repo\n\nExisting content.\n", encoding="utf-8")
        policy = load_policy(None)
        write_hardening_files(tmp_path, "testowner", policy)
        readme = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "Existing content." in readme
        assert "## License" in readme

    def test_no_security_workflow_when_disabled(self, tmp_path: Path) -> None:
        policy = {**_POLICY_DEFAULTS, "security_workflow": False}
        write_hardening_files(tmp_path, "testowner", policy)
        assert not (tmp_path / ".github" / "workflows" / "security.yml").exists()

    def test_dependabot_detects_npm(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        policy = load_policy(None)
        write_hardening_files(tmp_path, "testowner", policy)
        dependabot = (tmp_path / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        assert 'package-ecosystem: "npm"' in dependabot

    def test_codeowners_uses_owner(self, tmp_path: Path) -> None:
        policy = load_policy(None)
        write_hardening_files(tmp_path, "myowner", policy)
        codeowners = (tmp_path / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        assert "@myowner" in codeowners

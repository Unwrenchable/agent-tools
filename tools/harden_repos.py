from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from pathlib import Path
from typing import Any

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import run  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "policy.json"

# ── helpers ────────────────────────────────────────────────────────────────────


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ── policy ─────────────────────────────────────────────────────────────────────

_POLICY_DEFAULTS: dict[str, Any] = {
    "license_mode": "non-commercial",
    "license_contact": "",
    "approvals_required": 1,
    "codeowners_protected_paths": [
        ".github/workflows/**",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Pipfile.lock",
        "poetry.lock",
        "Cargo.lock",
        "go.sum",
        "composer.lock",
        "Gemfile.lock",
        "Package.resolved",
        ".releaserc",
        ".releaserc.json",
        ".releaserc.yml",
        ".releaserc.yaml",
        ".releaserc.js",
        "release.config.js",
        "release.config.ts",
        ".github/workflows/release*.yml",
        ".github/workflows/publish*.yml",
        ".github/workflows/deploy*.yml",
    ],
    "dependabot_schedule": "weekly",
    "security_workflow": True,
    "branch_protection": {
        "require_pr": True,
        "approvals_required": 1,
        "dismiss_stale_reviews": True,
        "require_conversation_resolution": True,
    },
}


def load_policy(path: Path | None = None) -> dict:
    """Load policy.json, merging with built-in defaults."""
    resolved = path or DEFAULT_POLICY_PATH
    base: dict = dict(_POLICY_DEFAULTS)
    if resolved.exists():
        loaded = json.loads(resolved.read_text(encoding="utf-8"))
        # Deep-merge branch_protection sub-dict
        if "branch_protection" in loaded and isinstance(loaded["branch_protection"], dict):
            merged_bp = dict(base["branch_protection"])
            merged_bp.update(loaded["branch_protection"])
            loaded["branch_protection"] = merged_bp
        base.update(loaded)
    return base


# ── ecosystem detection for dependabot ────────────────────────────────────────

_ECOSYSTEM_FILES: list[tuple[str, str]] = [
    ("package.json", "npm"),
    ("requirements.txt", "pip"),
    ("Pipfile", "pip"),
    ("pyproject.toml", "pip"),
    ("Cargo.toml", "cargo"),
    ("go.mod", "gomod"),
    ("pom.xml", "maven"),
    ("build.gradle", "gradle"),
    ("build.gradle.kts", "gradle"),
    ("Gemfile", "bundler"),
    ("composer.json", "composer"),
    ("Package.swift", "swift"),
    ("*.csproj", "nuget"),
    ("*.sln", "nuget"),
]


def detect_ecosystems(repo_path: Path) -> list[str]:
    """Return deduplicated list of Dependabot ecosystem names detected in *repo_path*."""
    found: list[str] = []
    seen: set[str] = set()

    def _add(eco: str) -> None:
        if eco not in seen:
            seen.add(eco)
            found.append(eco)

    for pattern, eco in _ECOSYSTEM_FILES:
        if "*" in pattern:
            if any(repo_path.glob(pattern)):
                _add(eco)
        elif (repo_path / pattern).exists():
            _add(eco)

    # GitHub Actions is always relevant when .github/workflows/ exists
    if (repo_path / ".github" / "workflows").is_dir():
        _add("github-actions")

    return found


# ── file generators ────────────────────────────────────────────────────────────


def build_security_md() -> str:
    return """\
# Security Policy

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.**

To report a security vulnerability privately, use one of the following options:

- **GitHub Private Vulnerability Reporting** (preferred):
  Go to the repository's **Security** tab → **Advisories** → **Report a vulnerability**.
- **Email**: If private reporting is not enabled on this repository, email the
  maintainer directly. Check the repository's README or profile for contact details.

When reporting, please include:
- A clear description of the issue
- Steps to reproduce the vulnerability
- The potential impact (what can an attacker do?)
- Any suggested mitigations or patches you have in mind

You can expect an initial acknowledgement within **72 hours** and a resolution
timeline within **90 days**, depending on severity.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest  | ✅ Yes    |
| Older   | ❌ No     |

Only the latest release on the default branch is actively maintained with
security patches. If you are using an older version, please upgrade before
reporting a vulnerability.

## Disclosure Policy

- We follow a **coordinated disclosure** model.
- We ask that you give us reasonable time to address the issue before any
  public disclosure.
- We will credit reporters in the security advisory unless you prefer to remain
  anonymous.
- Critical vulnerabilities (CVSS ≥ 9.0) will be addressed as a priority fix.

## Security Best Practices for Contributors

- Never commit secrets, API keys, or credentials to this repository.
- Review dependency updates for known CVEs before merging.
- Follow the principle of least privilege in any code that handles
  authentication, authorization, or external API calls.
"""


def build_codeowners(owner: str, protected_paths: list[str]) -> str:
    owner_handle = f"@{owner.lstrip('@')}"
    lines = [
        "# CODEOWNERS — sensitive paths that require a maintainer review on every PR.",
        "# See https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners",
        "",
        "# Default owner for everything not matched below",
        f"*  {owner_handle}",
        "",
        "# CI/CD workflows — any change here is security-sensitive",
        f".github/workflows/**  {owner_handle}",
        "",
        "# Dependency manifests and lockfiles",
    ]
    # Add any extra paths from policy (skip the ones already added above)
    already_added = {".github/workflows/**"}
    for path in protected_paths:
        if path not in already_added:
            lines.append(f"{path}  {owner_handle}")
    return "\n".join(lines) + "\n"


_KNOWN_ECOSYSTEMS: frozenset[str] = frozenset(
    {
        "npm", "pip", "cargo", "gomod", "maven", "gradle",
        "bundler", "composer", "nuget", "swift", "github-actions",
    }
)


def _dependabot_entry(eco: str, interval: str) -> str:
    """Return a single Dependabot update block for *eco*."""
    lines = [
        f'  - package-ecosystem: "{eco}"',
        '    directory: "/"',
        "    schedule:",
        f'      interval: "{interval}"',
    ]
    # github-actions updates are always few; no need to cap the PR limit.
    if eco != "github-actions":
        lines.append("    open-pull-requests-limit: 10")
    return "\n".join(lines) + "\n"


def build_dependabot_yml(ecosystems: list[str], schedule: str) -> str:
    interval = schedule.lower()
    if interval not in ("daily", "weekly", "monthly"):
        interval = "weekly"

    updates = [
        _dependabot_entry(eco, interval)
        for eco in ecosystems
        if eco in _KNOWN_ECOSYSTEMS
    ]

    if not updates:
        # Always include github-actions as a safe minimum
        updates.append(_dependabot_entry("github-actions", interval))

    return "version: 2\nupdates:\n" + "".join(updates)


def build_pr_template() -> str:
    return """\
## Description

<!-- What does this PR do? Why is this change needed? -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] Dependency update
- [ ] Security fix

## Security Checklist

<!-- Complete all items before requesting a review. -->

- [ ] **Dependency changes**: Any added/updated/removed dependencies have been
  reviewed for known CVEs (e.g., via `npm audit`, `pip-audit`, `cargo audit`).
- [ ] **Workflow changes**: Any changes to `.github/workflows/` follow least-privilege
  principles — `permissions` are scoped, no `pull_request_target` with untrusted code,
  no unpin actions without hash-pinning.
- [ ] **Secrets**: No credentials, tokens, API keys, or private data are committed.
  All secrets are injected via environment variables or GitHub Secrets.
- [ ] **Tests**: New or modified logic has tests. Existing tests still pass.
- [ ] **Input validation**: Any new user-facing inputs are validated and sanitized.
- [ ] **Scope**: The PR is focused and does not include unrelated changes.

## Testing

<!-- Describe how you tested these changes (commands run, environments used, etc.) -->

## Related Issues

<!-- Closes # -->
"""


def build_security_workflow() -> str:
    return """\
name: Security Scan

on:
  push:
    branches: ["main", "master"]
  pull_request:
    branches: ["main", "master"]
  schedule:
    - cron: "0 6 * * 1"

permissions:
  contents: read

jobs:
  dependency-review:
    name: Dependency Review
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Dependency Review
        uses: actions/dependency-review-action@v4

  secret-scan:
    name: Secret Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Run Gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
"""


_NC_LICENSE_TEMPLATE = """\
Non-Commercial Source License

Copyright (c) {year} {holder}

Permission is granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to use, copy,
modify, merge, and distribute the Software for non-commercial purposes only,
subject to the following conditions:

1. Non-Commercial Use Only.
   "Non-Commercial" means not primarily intended for or directed towards
   commercial advantage or monetary compensation. Academic research, personal
   projects, and open-source contributions qualify as non-commercial use.
   If you are unsure whether your use qualifies, contact the copyright holder.

2. Commercial Use.
   Commercial use of this Software requires prior written permission from the
   copyright holder.{contact_clause}

3. Attribution.
   The above copyright notice and this permission notice shall be included in
   all copies or substantial portions of the Software.

4. Redistribution.
   Redistribution of modified versions must carry this same license and clearly
   indicate the changes made from the original.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_DUAL_LICENSE_HEADER = """\
Dual-License

This software is available under a dual-license model:

  Non-Commercial Use:  Licensed under the Non-Commercial Source License below.
  Commercial Use:      Contact {contact} to obtain a commercial license.

─────────────────────────────────────────────────────────────────────────────
Non-Commercial Source License
─────────────────────────────────────────────────────────────────────────────

"""


def build_license_text(policy: dict, copyright_year: int, copyright_holder: str) -> str:
    contact = (policy.get("license_contact") or "").strip()
    contact_clause = (
        f"\n   To obtain a commercial license, contact: {contact}" if contact else ""
    )
    nc_text = _NC_LICENSE_TEMPLATE.format(
        year=copyright_year,
        holder=copyright_holder,
        contact_clause=contact_clause,
    )
    if policy.get("license_mode") == "dual":
        header = _DUAL_LICENSE_HEADER.format(contact=contact or "<your-contact>")
        return header + nc_text
    return nc_text


_LICENSE_README_BLOCK_MARKER = "<!-- agentx-license-summary -->"
_LICENSE_SECTION_PATTERN = re.compile(
    r"## License\n.*?(?=\n## |\Z)", re.DOTALL
)


def _build_license_readme_block(policy: dict, owner: str) -> str:
    mode = policy.get("license_mode", "non-commercial")
    contact = (policy.get("license_contact") or "").strip()
    if mode == "dual":
        contact_str = f" · Commercial license: {contact}" if contact else " · Commercial license: contact the maintainer"
        return (
            f"## License\n\n"
            f"{_LICENSE_README_BLOCK_MARKER}\n"
            f"This project is available under a **dual-license** model.\n\n"
            f"- **Non-Commercial Use** — free to use, modify, and distribute for non-commercial purposes.\n"
            f"- **Commercial Use** — requires a separate commercial license.{contact_str}\n\n"
            f"See [LICENSE](LICENSE) for the full terms.\n"
        )
    return (
        f"## License\n\n"
        f"{_LICENSE_README_BLOCK_MARKER}\n"
        f"This project is licensed for **non-commercial use only**.\n"
        f"Commercial use requires prior written permission from @{owner}.\n"
        f"See [LICENSE](LICENSE) for the full terms.\n"
    )


def update_readme_with_license(readme_text: str, policy: dict, owner: str) -> str:
    """Insert or replace the License section in *readme_text*."""
    block = _build_license_readme_block(policy, owner)
    # Replace existing License section if present
    if _LICENSE_SECTION_PATTERN.search(readme_text):
        return _LICENSE_SECTION_PATTERN.sub(block.rstrip("\n") + "\n", readme_text)
    # Append at end
    separator = "\n\n" if not readme_text.endswith("\n\n") else ""
    return readme_text.rstrip("\n") + separator + "\n" + block


# ── file writing ────────────────────────────────────────────────────────────────


def write_hardening_files(
    repo_path: Path,
    owner: str,
    policy: dict,
    copyright_year: int | None = None,
    repo_name: str | None = None,
) -> None:
    """Write all security hardening files into *repo_path*."""
    year = copyright_year or date.today().year
    github_dir = repo_path / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)

    # SECURITY.md
    (repo_path / "SECURITY.md").write_text(build_security_md(), encoding="utf-8")

    # .github/CODEOWNERS
    protected = list(policy.get("codeowners_protected_paths") or [])
    (github_dir / "CODEOWNERS").write_text(
        build_codeowners(owner, protected), encoding="utf-8"
    )

    # .github/dependabot.yml
    ecosystems = detect_ecosystems(repo_path)
    schedule = str(policy.get("dependabot_schedule") or "weekly")
    (github_dir / "dependabot.yml").write_text(
        build_dependabot_yml(ecosystems, schedule), encoding="utf-8"
    )

    # .github/pull_request_template.md
    (github_dir / "pull_request_template.md").write_text(
        build_pr_template(), encoding="utf-8"
    )

    # .github/workflows/security.yml (optional)
    if policy.get("security_workflow", True):
        workflows_dir = github_dir / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "security.yml").write_text(
            build_security_workflow(), encoding="utf-8"
        )

    # LICENSE
    license_text = build_license_text(policy, year, owner)
    (repo_path / "LICENSE").write_text(license_text, encoding="utf-8")

    # README update
    readme_path = repo_path / "README.md"
    if readme_path.exists():
        original = readme_path.read_text(encoding="utf-8")
        updated = update_readme_with_license(original, policy, owner)
        readme_path.write_text(updated, encoding="utf-8")
    else:
        display_name = repo_name or repo_path.name
        readme_path.write_text(
            f"# {display_name}\n\n"
            + _build_license_readme_block(policy, owner),
            encoding="utf-8",
        )


# ── repo settings via GitHub API ───────────────────────────────────────────────


@dataclass(slots=True)
class SettingResult:
    name: str
    status: str  # "applied" | "skipped" | "error"
    message: str = ""


def _gh_api(
    method: str,
    endpoint: str,
    body: dict | None = None,
) -> tuple[bool, str]:
    """Run a gh api call. Returns (success, output_or_error)."""
    cmd = ["gh", "api", "--method", method, endpoint]
    if body:
        cmd += ["--input", "-"]
    try:
        process = subprocess.run(
            cmd,
            input=json.dumps(body) if body else None,
            capture_output=True,
            text=True,
        )
        if process.returncode == 0:
            return True, process.stdout.strip()
        return False, (process.stderr or process.stdout).strip()
    except Exception as exc:
        return False, str(exc)


def apply_repo_settings(
    name_with_owner: str,
    default_branch: str,
    policy: dict,
    dry_run: bool,
) -> list[SettingResult]:
    results: list[SettingResult] = []
    owner = name_with_owner.split("/")[0]
    repo = name_with_owner.split("/")[1]
    bp = policy.get("branch_protection") or {}
    approvals = int(bp.get("approvals_required", policy.get("approvals_required", 1)))

    # ── 1. Branch protection ─────────────────────────────────────────────────
    protection_body = {
        "required_status_checks": None,
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": bool(bp.get("dismiss_stale_reviews", True)),
            "require_code_owner_reviews": True,
            "required_approving_review_count": approvals,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_conversation_resolution": bool(
            bp.get("require_conversation_resolution", True)
        ),
        "allow_force_pushes": False,
        "allow_deletions": False,
    }
    if dry_run:
        results.append(
            SettingResult(
                name="branch_protection",
                status="skipped",
                message=f"dry-run: would apply to {default_branch}",
            )
        )
    else:
        ok, out = _gh_api(
            "PUT",
            f"/repos/{owner}/{repo}/branches/{default_branch}/protection",
            protection_body,
        )
        results.append(
            SettingResult(
                name="branch_protection",
                status="applied" if ok else "error",
                message="" if ok else out,
            )
        )

    # ── 2. Actions workflow default permissions ────────────────────────────
    workflow_perms = {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    if dry_run:
        results.append(
            SettingResult(
                name="actions_permissions",
                status="skipped",
                message="dry-run: would set default_workflow_permissions=read",
            )
        )
    else:
        ok, out = _gh_api(
            "PUT",
            f"/repos/{owner}/{repo}/actions/permissions/workflow",
            workflow_perms,
        )
        results.append(
            SettingResult(
                name="actions_permissions",
                status="applied" if ok else "error",
                message="" if ok else out,
            )
        )

    # ── 3. Dependabot alerts ────────────────────────────────────────────────
    if dry_run:
        results.append(
            SettingResult(
                name="dependabot_alerts",
                status="skipped",
                message="dry-run: would enable vulnerability-alerts",
            )
        )
    else:
        ok, out = _gh_api("PUT", f"/repos/{owner}/{repo}/vulnerability-alerts")
        # A 204 is success but gh returns empty stdout; a non-zero rc means failure
        results.append(
            SettingResult(
                name="dependabot_alerts",
                status="applied" if ok else "error",
                message="" if ok else out,
            )
        )

    # ── 4. Dependabot security updates ─────────────────────────────────────
    if dry_run:
        results.append(
            SettingResult(
                name="dependabot_security_updates",
                status="skipped",
                message="dry-run: would enable automated-security-fixes",
            )
        )
    else:
        ok, out = _gh_api("PUT", f"/repos/{owner}/{repo}/automated-security-fixes")
        results.append(
            SettingResult(
                name="dependabot_security_updates",
                status="applied" if ok else "error",
                message="" if ok else out,
            )
        )

    # ── 5. Secret scanning + push protection (GitHub Advanced Security) ────
    secret_scanning_body = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        }
    }
    if dry_run:
        results.append(
            SettingResult(
                name="secret_scanning",
                status="skipped",
                message="dry-run: would enable secret_scanning and push_protection",
            )
        )
    else:
        ok, out = _gh_api("PATCH", f"/repos/{owner}/{repo}", secret_scanning_body)
        if ok:
            results.append(SettingResult(name="secret_scanning", status="applied"))
        else:
            # Feature may not be available (e.g., free public repos without GHAS)
            results.append(
                SettingResult(
                    name="secret_scanning",
                    status="error",
                    message=f"not available or insufficient permissions: {out}",
                )
            )

    return results


# ── per-repo orchestrator ──────────────────────────────────────────────────────


@dataclass(slots=True)
class HardeningResult:
    repo: str
    status: str  # "pr_opened" | "dry_run" | "no_changes" | "settings_only" | "failed" | "skipped"
    pr_url: str = ""
    settings: list[dict] = field(default_factory=list)
    message: str = ""


def harden_repo(
    workdir: Path,
    repo: dict,
    owner: str,
    policy: dict,
    branch: str,
    mode: str,
    dry_run: bool,
) -> HardeningResult:
    name_with_owner = str(repo["nameWithOwner"])
    repo_name = name_with_owner.split("/", 1)[1]
    default_branch = (repo.get("defaultBranchRef") or {}).get("name") or "main"
    local_path = workdir / repo_name

    settings_results: list[dict] = []
    pr_url = ""
    file_status = ""

    # ── settings mode ────────────────────────────────────────────────────────
    if mode in ("settings", "all"):
        raw = apply_repo_settings(name_with_owner, default_branch, policy, dry_run)
        settings_results = [asdict(r) for r in raw]

    # ── files mode ───────────────────────────────────────────────────────────
    if mode in ("files", "all"):
        try:
            if local_path.exists():
                shutil.rmtree(local_path)

            run(["git", "clone", f"https://github.com/{name_with_owner}.git", str(local_path)])
            run(["git", "checkout", "-B", branch], cwd=local_path)

            write_hardening_files(local_path, owner, policy, repo_name=repo_name)

            git_status = run(["git", "status", "--porcelain"], cwd=local_path)
            if not git_status:
                file_status = "no_changes"
            elif dry_run:
                file_status = "dry_run"
            else:
                run(["git", "add", "."], cwd=local_path)
                run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "chore(security): add repo hardening baseline",
                    ],
                    cwd=local_path,
                )
                run(["git", "push", "-u", "origin", branch], cwd=local_path)

                body = (
                    "Adds a security hardening baseline for this repository:\n\n"
                    "- `SECURITY.md`: private vulnerability reporting, supported versions, "
                    "and disclosure expectations\n"
                    "- `.github/CODEOWNERS`: owner review required for workflows, "
                    "lockfiles, and release configs\n"
                    "- `.github/dependabot.yml`: automated dependency and GitHub Actions "
                    "update PRs\n"
                    "- `.github/pull_request_template.md`: security checklist for every PR\n"
                    "- `.github/workflows/security.yml`: lightweight dependency review and "
                    "secret scanning\n"
                    "- `LICENSE`: non-commercial source license\n"
                    "- `README.md`: license summary section added/updated\n\n"
                    "Generated by `tools/harden_repos.py` from `policy.json`.\n"
                )
                pr_url = run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        name_with_owner,
                        "--base",
                        default_branch,
                        "--head",
                        branch,
                        "--title",
                        "chore(security): add repo hardening baseline",
                        "--body",
                        body,
                    ]
                )
                file_status = "pr_opened"
        except Exception as exc:
            return HardeningResult(
                repo=name_with_owner,
                status="failed",
                settings=settings_results,
                message=str(exc),
            )

    # ── determine overall status ─────────────────────────────────────────────
    if mode == "settings":
        overall = "settings_only" if not dry_run else "dry_run"
    elif file_status == "pr_opened":
        overall = "pr_opened"
    elif file_status == "dry_run":
        overall = "dry_run"
    elif file_status == "no_changes":
        overall = "no_changes"
    else:
        overall = "settings_only" if settings_results else "no_changes"

    return HardeningResult(
        repo=name_with_owner,
        status=overall,
        pr_url=pr_url,
        settings=settings_results,
    )


# ── repo listing ───────────────────────────────────────────────────────────────


def get_repos(owner: str, limit: int) -> list[dict]:
    payload = run(
        [
            "gh",
            "repo",
            "list",
            owner,
            "--limit",
            str(limit),
            "--json",
            "nameWithOwner,isPrivate,url,defaultBranchRef,isArchived",
        ]
    )
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("Unexpected GitHub response")
    return data


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Harden GitHub repos: open security-file PRs and/or apply "
            "branch protection + Actions settings."
        )
    )
    parser.add_argument("--owner", required=True, help="GitHub owner/org")
    parser.add_argument("--limit", type=int, default=200, help="Max repos to process")
    parser.add_argument(
        "--workdir",
        default="/tmp/agentx-hardening",
        help="Local workspace for cloning repos (files mode only)",
    )
    parser.add_argument(
        "--branch",
        default=f"security-hardening-{date.today().isoformat()}",
        help="Branch name for file-change PRs",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY_PATH),
        help="Path to policy.json",
    )
    parser.add_argument(
        "--repos",
        nargs="*",
        metavar="REPO",
        help="Specific repo names to target (e.g. my-repo). Omit to process all.",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--hardening-files",
        dest="mode",
        action="store_const",
        const="files",
        help="Open PRs adding security files only",
    )
    mode_group.add_argument(
        "--hardening-settings",
        dest="mode",
        action="store_const",
        const="settings",
        help="Apply GitHub repo settings only (no file PRs)",
    )
    mode_group.add_argument(
        "--hardening-all",
        dest="mode",
        action="store_const",
        const="all",
        help="Apply both file PRs and repo settings",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually make changes. Without this flag the script runs in dry-run mode.",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    run(["gh", "auth", "status"])

    policy = load_policy(Path(args.policy))
    repos = [r for r in get_repos(args.owner, args.limit) if not r.get("isArchived")]

    if args.repos:
        target_set = set(args.repos)
        repos = [r for r in repos if r["nameWithOwner"].split("/", 1)[1] in target_set]

    workdir = Path(args.workdir)
    if args.mode in ("files", "all"):
        workdir.mkdir(parents=True, exist_ok=True)

    results: list[HardeningResult] = []
    for repo in repos:
        results.append(
            harden_repo(
                workdir=workdir,
                repo=repo,
                owner=args.owner,
                policy=policy,
                branch=args.branch,
                mode=args.mode,
                dry_run=dry_run,
            )
        )

    summary = {
        "owner": args.owner,
        "branch": args.branch,
        "mode": args.mode,
        "dry_run": dry_run,
        "total": len(results),
        "pr_opened": len([r for r in results if r.status == "pr_opened"]),
        "dry_run_ready": len([r for r in results if r.status == "dry_run"]),
        "settings_only": len([r for r in results if r.status == "settings_only"]),
        "no_changes": len([r for r in results if r.status == "no_changes"]),
        "failed": len([r for r in results if r.status == "failed"]),
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

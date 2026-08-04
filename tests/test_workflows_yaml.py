"""Structural checks on the GitHub Actions workflows this repo ships.

These tests guard *shape* only (triggers, matrix, jobs, inputs, permissions) —
actual execution is proven by CI itself running the workflows, not by this
file. Keep assertions structural so the workflows stay free to evolve their
step internals without breaking tests here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
CI_YML = WORKFLOWS_DIR / "ci.yml"
GRAPHSPEC_VALIDATE_YML = WORKFLOWS_DIR / "graphspec-validate.yml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def on_section(doc: dict[str, Any]) -> Any:
    """Fetch the workflow-level ``on:`` mapping.

    PyYAML's default (YAML 1.1) resolver treats the bare unquoted key ``on``
    as the boolean ``True`` — the classic GitHub Actions gotcha. Handle both
    so this test is not itself fooled by the same trap it is guarding
    against.
    """
    if "on" in doc:
        return doc["on"]
    return doc[True]


def all_run_strings(node: Any) -> list[str]:
    """Recursively collect every string found under a ``run:`` key."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(all_run_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(all_run_strings(item))
    return found


def steps_of(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job.get("steps", [])


def job_text(job: dict[str, Any]) -> str:
    """Flatten a job's run/env/with strings for substring assertions.

    Untrusted expressions like `${{ inputs.file }}` belong in `env:`, not
    interpolated straight into `run:` — so structural checks must look at the
    whole step (env included), not just the run script.
    """
    return yaml.safe_dump(job, sort_keys=False)


def uses_names(job: dict[str, Any]) -> list[str]:
    return [step["uses"] for step in steps_of(job) if "uses" in step]


# ---------------------------------------------------------------------------
# ci.yml
# ---------------------------------------------------------------------------


class TestCiYml:
    def test_file_exists_and_parses(self) -> None:
        assert CI_YML.is_file()
        doc = load_yaml(CI_YML)
        assert isinstance(doc, dict)

    def test_triggers_on_push_to_main_and_pull_request(self) -> None:
        doc = load_yaml(CI_YML)
        triggers = on_section(doc)
        assert "push" in triggers
        assert "main" in triggers["push"]["branches"]
        assert "pull_request" in triggers

    def test_python_matrix_covers_3_11_3_12_3_13(self) -> None:
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        matrix_versions: set[str] = set()
        for job in jobs.values():
            strategy = job.get("strategy")
            if not strategy:
                continue
            matrix = strategy.get("matrix", {})
            versions = matrix.get("python-version")
            if versions:
                matrix_versions.update(str(v) for v in versions)
        assert {"3.11", "3.12", "3.13"} <= matrix_versions

    def test_matrix_job_installs_dev_extras_and_runs_pytest(self) -> None:
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        matrix_job = next(j for j in jobs.values() if j.get("strategy", {}).get("matrix", {}).get("python-version"))
        runs = all_run_strings(matrix_job)
        joined = "\n".join(runs)
        assert ".[dev]" in joined
        assert "pytest" in joined

    def test_matrix_job_lints_with_compileall(self) -> None:
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        matrix_job = next(j for j in jobs.values() if j.get("strategy", {}).get("matrix", {}).get("python-version"))
        joined = "\n".join(all_run_strings(matrix_job))
        assert "compileall" in joined
        assert "graphspec" in joined

    def test_matrix_job_validates_all_three_examples_and_renders_dot(self) -> None:
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        matrix_job = next(j for j in jobs.values() if j.get("strategy", {}).get("matrix", {}).get("python-version"))
        joined = "\n".join(all_run_strings(matrix_job))

        assert "graphspec validate" in joined
        for example in (
            "examples/software-delivery.yaml",
            "examples/research-publishing.yaml",
            "examples/support-triage.yaml",
        ):
            assert example in joined

        assert "graphspec render examples/software-delivery.yaml" in joined
        assert "/dev/null" in joined

    def test_matrix_job_requires_no_graphviz(self) -> None:
        """The whole point of the matrix job's validate step: it proves DOT
        rendering needs no Graphviz install. Assert that job never installs
        graphviz."""
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        matrix_job = next(j for j in jobs.values() if j.get("strategy", {}).get("matrix", {}).get("python-version"))
        joined = "\n".join(all_run_strings(matrix_job)).lower()
        assert "graphviz" not in joined
        assert "apt-get" not in joined

    def test_extra_job_installs_graphviz_and_renders_svg(self) -> None:
        doc = load_yaml(CI_YML)
        jobs = doc["jobs"]
        svg_jobs = [
            job
            for job in jobs.values()
            if "graphviz" in "\n".join(all_run_strings(job)).lower()
        ]
        assert svg_jobs, "expected one job that installs graphviz to cover the shell-out path"
        svg_job = svg_jobs[0]
        joined = "\n".join(all_run_strings(svg_job))
        assert "apt" in joined.lower()
        assert "--format svg" in joined
        assert "/dev/null" in joined
        # This job must run on ubuntu (apt-get needs it) and should not itself
        # be the cross-platform matrix job.
        assert svg_job.get("runs-on") == "ubuntu-latest" or "ubuntu" in str(svg_job.get("runs-on", ""))

    def test_uses_checkout_and_setup_python(self) -> None:
        doc = load_yaml(CI_YML)
        for job in doc["jobs"].values():
            actions = uses_names(job)
            assert any(a.startswith("actions/checkout@") for a in actions)
            assert any(a.startswith("actions/setup-python@") for a in actions)


# ---------------------------------------------------------------------------
# graphspec-validate.yml
# ---------------------------------------------------------------------------


class TestGraphspecValidateYml:
    def test_file_exists_and_parses(self) -> None:
        assert GRAPHSPEC_VALIDATE_YML.is_file()
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        assert isinstance(doc, dict)

    def test_declares_workflow_call_with_file_and_python_version_inputs(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        triggers = on_section(doc)
        assert "workflow_call" in triggers
        inputs = triggers["workflow_call"]["inputs"]

        assert "file" in inputs
        assert inputs["file"]["default"] == "./graphspec.yaml"

        assert "python-version" in inputs
        assert str(inputs["python-version"]["default"]) == "3.12"

    def test_declares_three_jobs(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        assert len(jobs) == 3
        assert "validate" in jobs
        diff_job_names = [name for name in jobs if "diff" in name]
        render_job_names = [name for name in jobs if "render" in name]
        assert diff_job_names, "expected a diff/comment job"
        assert render_job_names, "expected a render-artifact job"

    def test_validate_job_installs_and_runs_graphspec_validate(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        job = doc["jobs"]["validate"]
        joined = "\n".join(all_run_strings(job))
        assert "pip install graphspec" in joined
        assert "graphspec validate" in joined
        # inputs.file must reach the validate command, whether interpolated
        # directly or (safer) threaded through an env var.
        assert "inputs.file" in job_text(job)

    def test_diff_job_only_runs_on_pull_request(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        diff_job = next(job for name, job in jobs.items() if "diff" in name)
        condition = diff_job.get("if", "")
        assert "pull_request" in condition

    def test_diff_job_materializes_base_and_runs_graphspec_diff(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        diff_job = next(job for name, job in jobs.items() if "diff" in name)
        joined = "\n".join(all_run_strings(diff_job))
        text = job_text(diff_job)
        assert "git show" in joined and "origin/" in joined
        assert "base_ref" in text  # either interpolated or via an env var
        assert "graphspec diff" in joined
        assert "--format markdown" in joined

    def test_diff_job_does_not_fail_the_job_on_diff_exit_1(self) -> None:
        """`graphspec diff` exits 1 when there ARE changes — that is data,
        not failure. The step invoking it must not let that exit code fail
        the job."""
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        diff_job = next(job for name, job in jobs.items() if "diff" in name)
        diff_steps = [
            step
            for step in steps_of(diff_job)
            if "graphspec diff" in step.get("run", "")
        ]
        assert diff_steps
        for step in diff_steps:
            run = step["run"]
            tolerates_failure = (
                "|| true" in run
                or "continue-on-error" in step
                or step.get("continue-on-error") is True
            )
            assert tolerates_failure

    def test_diff_job_uses_github_script_to_post_comment(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        diff_job = next(job for name, job in jobs.items() if "diff" in name)
        actions = uses_names(diff_job)
        assert any(a.startswith("actions/github-script@") for a in actions)

    def test_diff_job_upsert_marker_guards_empty_diff(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        diff_job = next(job for name, job in jobs.items() if "diff" in name)
        script_step = next(
            step for step in steps_of(diff_job) if step.get("uses", "").startswith("actions/github-script@")
        )
        script = script_step["with"]["script"]
        assert "<!--" in script  # HTML marker comment for upsert
        assert "listComments" in script
        assert "updateComment" in script
        assert "createComment" in script

    def test_render_job_installs_graphviz_and_uploads_svg_artifact(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        jobs = doc["jobs"]
        render_job = next(job for name, job in jobs.items() if "render" in name)
        joined = "\n".join(all_run_strings(render_job))
        assert "graphviz" in joined.lower()
        assert "--format svg" in joined
        actions = uses_names(render_job)
        assert any(a.startswith("actions/upload-artifact@") for a in actions)

    def test_permissions_include_contents_read_and_pull_requests_write(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        # permissions may be declared at workflow level and/or per job; check
        # that pull-requests: write is granted *somewhere* reachable by the
        # comment-posting job, and contents: read is declared at least once.
        workflow_perms = doc.get("permissions", {})
        all_perms = [workflow_perms]
        for job in doc["jobs"].values():
            if "permissions" in job:
                all_perms.append(job["permissions"])

        assert any(p.get("contents") == "read" for p in all_perms)
        assert any(p.get("pull-requests") == "write" for p in all_perms)

    def test_pinned_action_majors(self) -> None:
        doc = load_yaml(GRAPHSPEC_VALIDATE_YML)
        all_actions: list[str] = []
        for job in doc["jobs"].values():
            all_actions.extend(uses_names(job))

        expected_prefixes = {
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/github-script@v7",
            "actions/upload-artifact@v4",
        }
        for prefix in expected_prefixes:
            assert any(a == prefix for a in all_actions), f"expected pinned action {prefix} to be used"

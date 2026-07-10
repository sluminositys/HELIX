from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from lattice.runtime.script_drafting import (
    LangChainScriptDraftProvider,
    ScriptDraftProvider,
    UnavailableScriptDraftProvider,
)
from lattice.schemas import (
    AgenticExecutionPlan,
    ArtifactManifest,
    Provenance,
    ResearchTask,
    ResultVerificationReport,
    RunRecord,
    RuntimeGraphContext,
    ScriptExecutionRawResult,
    ScriptProposal,
    ScriptReviewResult,
)
from lattice.skill import SkillContext

BLOCKED_SCRIPT_MARKERS = (
    "Remove-Item",
    "rm -rf",
    "git reset --hard",
    "git clean",
    "format ",
    "Invoke-WebRequest",
    "curl ",
    "wget ",
    "os.remove(",
    "os.unlink(",
    "shutil.rmtree(",
    ".unlink(",
)

NETWORK_MODULES = {"httpx", "requests", "socket", "urllib", "ftplib"}


class ScriptGenerationAgent:
    def __init__(self, provider: ScriptDraftProvider | None = None) -> None:
        self.provider = provider or UnavailableScriptDraftProvider()

    @classmethod
    def from_model_settings(cls, settings: Any) -> ScriptGenerationAgent:
        provider = str(getattr(settings, "chat_provider", "not_configured"))
        model = str(getattr(settings, "chat_model", "not_configured"))
        if provider == "not_configured" or model == "not_configured":
            return cls()
        return cls(LangChainScriptDraftProvider(provider=provider, model=model))

    def generate(
        self,
        *,
        request: str,
        task: ResearchTask,
        plan: AgenticExecutionPlan,
        runtime_context: RuntimeGraphContext,
        skill_contexts: list[SkillContext],
        previous_review: ScriptReviewResult | None = None,
        previous_execution: ScriptExecutionRawResult | None = None,
    ) -> ScriptProposal:
        skill_ids = sorted(
            {
                skill_id
                for step in plan.steps
                for skill_id in step.candidate_skill_ids
            }
        )
        tool_names = sorted({tool for step in plan.steps for tool in step.suggested_tool_names})
        prompt = self._build_prompt(
            request=request,
            task=task,
            plan=plan,
            runtime_context=runtime_context,
            skill_contexts=skill_contexts,
            previous_review=previous_review,
            previous_execution=previous_execution,
        )
        script_text = self.provider.draft(prompt)
        return ScriptProposal(
            proposal_id=f"script-{uuid4()}",
            plan_id=plan.plan_id,
            script_text=script_text,
            covered_step_ids=[step.step_id for step in plan.steps],
            intended_actions=[
                step.objective or step.step_id for step in plan.steps
            ],
            referenced_skill_ids=skill_ids,
            suggested_tool_names=tool_names,
            expected_artifacts=[
                artifact
                for step in plan.steps
                for artifact in step.expected_outputs
            ],
            permission_requirements=_merge_permissions(plan),
            environment_requirements=[
                requirement
                for context in skill_contexts
                for spec in context.environment_specs
                for requirement in _environment_requirements(spec)
            ],
            rationale=(
                "Generated from the research task, task-specific plan, G2 references, "
                "and agent-readable L5 Skill context."
            ),
            revision_of_proposal_id=(
                previous_review.proposal_id if previous_review is not None else None
            ),
            provenance=[
                Provenance(
                    source_type="script_generation_agent",
                    metadata={
                        "runtime_context_id": runtime_context.graph_context_id,
                        "skill_context_count": len(skill_contexts),
                    },
                )
            ],
        )

    def _build_prompt(
        self,
        *,
        request: str,
        task: ResearchTask,
        plan: AgenticExecutionPlan,
        runtime_context: RuntimeGraphContext,
        skill_contexts: list[SkillContext],
        previous_review: ScriptReviewResult | None,
        previous_execution: ScriptExecutionRawResult | None,
    ) -> str:
        compact_runtime = {
            "graph_context_id": runtime_context.graph_context_id,
            "workflow_nodes": _compact_nodes(runtime_context.G_workflow.nodes),
            "resource_nodes": _compact_nodes(runtime_context.G_resource.nodes),
            "experience_nodes": _compact_nodes(runtime_context.G_experience.nodes),
            "repair_advice_view": runtime_context.repair_advice_view,
            "quality_checkpoint_view": runtime_context.quality_checkpoint_view,
            "temporary_candidates": runtime_context.temporary_candidates,
        }
        payload = {
            "request": request,
            "research_task": task.model_dump(mode="json"),
            "execution_plan": plan.model_dump(mode="json"),
            "runtime_reference": compact_runtime,
            "skill_context": [context.model_dump(mode="json") for context in skill_contexts],
            "previous_review": previous_review.model_dump(mode="json")
            if previous_review is not None
            else None,
            "previous_execution_error": {
                "status": previous_execution.status,
                "exit_code": previous_execution.exit_code,
                "stderr": previous_execution.stderr[-4000:],
            }
            if previous_execution is not None
            else None,
        }
        return (
            "You are LATTICE's internal ScriptGenerationAgent. Generate one executable Python "
            "script for the supplied research task. G2 workflows, resources, and skills are "
            "references, not mandatory fixed paths. Use declared inputs only. Write all outputs "
            "under the current working directory. Check required inputs and dependencies, fail "
            "with a non-zero exit code when they are missing, preserve useful diagnostics, and do "
            "not claim success without producing the requested result. Do not access the network "
            "unless permission_requirements.network is true. Return only Python source code, with "
            "no markdown fence or explanation.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        )


class ScriptReviewAgent:
    def review(self, proposal: ScriptProposal) -> ScriptReviewResult:
        blockers = [
            f"blocked marker found in generated script: {marker}"
            for marker in BLOCKED_SCRIPT_MARKERS
            if marker.lower() in proposal.script_text.lower()
        ]
        warnings: list[str] = []
        revisions: list[str] = []
        try:
            tree = ast.parse(proposal.script_text)
        except SyntaxError as error:
            tree = None
            revisions.append(f"python syntax error at line {error.lineno}: {error.msg}")

        if tree is not None:
            network_imports = _network_imports(tree)
            if network_imports and not proposal.permission_requirements.get("network", False):
                blockers.append(
                    "undeclared network-capable imports: " + ", ".join(sorted(network_imports))
                )
            if _uses_subprocess(tree) and not proposal.permission_requirements.get("shell", False):
                blockers.append("the script starts a subprocess without declared shell permission")
            absolute_writes = _absolute_write_paths(tree)
            if absolute_writes:
                revisions.append(
                    "write outputs under the task working directory instead of absolute paths: "
                    + ", ".join(absolute_writes)
                )
        if not proposal.referenced_skill_ids:
            warnings.append("generated script has no referenced L5 skill ids")
        if proposal.language != "python":
            blockers.append(f"unsupported script language: {proposal.language}")
        if not proposal.covered_step_ids:
            revisions.append("declare which execution-plan steps the script covers")
        status: Literal["approved", "needs_revision", "blocked"] = (
            "blocked" if blockers else "needs_revision" if revisions else "approved"
        )
        return ScriptReviewResult(
            review_id=f"script-review-{uuid4()}",
            proposal_id=proposal.proposal_id,
            status=status,
            blockers=blockers,
            warnings=warnings,
            required_revisions=[*revisions, *blockers],
            static_findings={
                "line_count": len(proposal.script_text.splitlines()),
                "blocked_marker_count": len(blockers),
                "syntax_revision_count": len(revisions),
            },
            provenance=[Provenance(source_type="script_review_agent")],
        )


class ScriptRunner:
    def __init__(
        self,
        *,
        output_root: str | Path = "D:/workspace/codex/runs",
        timeout_seconds: int = 120,
    ) -> None:
        self.output_root = Path(output_root)
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        proposal: ScriptProposal,
        *,
        working_dir: str | Path | None = None,
    ) -> ScriptExecutionRawResult:
        started_at = datetime.now(timezone.utc)
        date_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        run_dir = (
            Path(working_dir)
            if working_dir is not None
            else self.output_root / date_dir / proposal.proposal_id
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        script_path = run_dir / f"{proposal.proposal_id}.py"
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        script_path.write_text(proposal.script_text, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(run_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            status: Literal["success", "failure"] = (
                "success" if completed.returncode == 0 else "failure"
            )
            artifacts = _discover_artifacts(run_dir)
            return ScriptExecutionRawResult(
                execution_id=f"script-exec-{uuid4()}",
                proposal_id=proposal.proposal_id,
                status=status,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                error_summary=(completed.stderr[-1000:] if completed.returncode != 0 else None),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                artifact_paths=artifacts,
                runtime_metadata={"working_dir": str(run_dir)},
                provenance=[Provenance(source_type="script_runner")],
            )
        except subprocess.TimeoutExpired as error:
            stdout = _to_text(error.stdout)
            stderr = _to_text(error.stderr)
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            return ScriptExecutionRawResult(
                execution_id=f"script-exec-{uuid4()}",
                proposal_id=proposal.proposal_id,
                status="timeout",
                stdout=stdout,
                stderr=stderr,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                error_summary=f"script exceeded {self.timeout_seconds} seconds",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                artifact_paths=_discover_artifacts(run_dir),
                runtime_metadata={"working_dir": str(run_dir)},
                provenance=[Provenance(source_type="script_runner")],
            )


class RunRecordBuilder:
    def build(
        self,
        *,
        session_id: str,
        request: str,
        plan: AgenticExecutionPlan | None,
        proposal: ScriptProposal | None,
        execution: ScriptExecutionRawResult | None,
        verification: ResultVerificationReport | None = None,
    ) -> tuple[RunRecord, ArtifactManifest]:
        provenance = [Provenance(source_type="run_record_builder")]
        manifest = ArtifactManifest(
            manifest_id=f"artifact-manifest-{uuid4()}",
            execution_id=execution.execution_id if execution is not None else "not-executed",
            artifacts=[
                _artifact_record(path)
                for path in (execution.artifact_paths if execution is not None else [])
            ],
            checks=[
                {
                    "name": "result_verification",
                    "status": verification.status,
                    "issues": verification.issues,
                }
            ]
            if verification is not None
            else [],
            provenance=provenance,
        )
        record = RunRecord(
            run_id=f"run-{uuid4()}",
            session_id=session_id,
            request=request,
            plan_id=plan.plan_id if plan is not None else None,
            proposal_id=proposal.proposal_id if proposal is not None else None,
            execution_id=execution.execution_id if execution is not None else None,
            status=execution.status if execution is not None else "skipped",
            referenced_skill_ids=proposal.referenced_skill_ids if proposal is not None else [],
            suggested_tool_names=proposal.suggested_tool_names if proposal is not None else [],
            artifact_manifest_id=manifest.manifest_id,
            result_summary=(
                "Task result verified."
                if verification is not None and verification.status == "completed"
                else "; ".join(verification.issues)
                if verification is not None
                else ""
            ),
            verification_status=verification.status if verification is not None else None,
            summary={
                "exit_code": execution.exit_code if execution is not None else None,
                "stdout_excerpt": (execution.stdout[:1000] if execution is not None else ""),
                "stderr_excerpt": (execution.stderr[:1000] if execution is not None else ""),
            },
            provenance=provenance,
        )
        return record, manifest


def _compact_nodes(nodes: list[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node.get("node_id"),
            "node_type": node.get("node_type"),
            "canonical_name": node.get("canonical_name"),
            "attributes": node.get("attributes", {}),
        }
        for node in nodes[:limit]
    ]


def _merge_permissions(plan: AgenticExecutionPlan) -> dict[str, Any]:
    permissions: dict[str, Any] = {"network": False, "shell": False, "write_workspace": True}
    for step in plan.steps:
        for key, value in step.permission_requirements.items():
            if isinstance(value, bool):
                permissions[key] = bool(permissions.get(key, False) or value)
            else:
                permissions[key] = value
    return permissions


def _environment_requirements(spec: dict[str, Any]) -> list[str]:
    attributes = spec.get("attributes", {})
    if not isinstance(attributes, dict):
        return []
    values = attributes.get("system_requirements", attributes.get("requirements", []))
    return [str(value) for value in values] if isinstance(values, list) else []


def _network_imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        imports.update(
            name.split(".")[0]
            for name in names
            if name.split(".")[0] in NETWORK_MODULES
        )
    return imports


def _uses_subprocess(tree: ast.AST) -> bool:
    process_calls = {
        "os.popen",
        "os.system",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    }
    return any(
        isinstance(node, ast.Call) and _call_name(node.func) in process_calls
        for node in ast.walk(tree)
    )


def _absolute_write_paths(tree: ast.AST) -> list[str]:
    paths: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = _call_name(node.func)
        if function_name not in {"open", "Path.write_text", "Path.write_bytes"}:
            continue
        path_value = _literal_write_target(node, function_name)
        if path_value is None:
            continue
        mode = ""
        if (
            function_name == "open"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
        ):
            mode = str(node.args[1].value)
        is_write = function_name != "open" or any(
            marker in mode for marker in ("w", "a", "+")
        )
        if is_write and Path(path_value).is_absolute():
            paths.append(path_value)
    return paths


def _literal_write_target(node: ast.Call, function_name: str) -> str | None:
    if function_name == "open":
        candidate = node.args[0] if node.args else None
    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
        path_call = node.func.value
        candidate = (
            path_call.args[0]
            if _call_name(path_call.func) == "Path" and path_call.args
            else None
        )
    else:
        candidate = None
    if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
        return candidate.value
    return None


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _call_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _discover_artifacts(run_dir: Path) -> list[str]:
    return sorted(str(path) for path in run_dir.rglob("*") if path.is_file())


def _artifact_record(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    record: dict[str, Any] = {"path": str(path), "kind": "runtime_file"}
    if not path.exists() or not path.is_file():
        record["exists"] = False
        return record
    record.update(
        {
            "exists": True,
            "size_bytes": path.stat().st_size,
            "checksum_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
    return record


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value

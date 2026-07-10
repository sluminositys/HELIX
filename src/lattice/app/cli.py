from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from lattice.config import load_settings
from lattice.db import PostgresSchemaManager
from lattice.graph import (
    FullGraphStore,
    GraphAssetImporter,
    GraphRecordStore,
    HealthyGraphStore,
    load_graph_records,
)
from lattice.graph.runtime_loader import GraphRuntimeLoadError, load_graph_runtime
from lattice.orchestration import run_execution, run_plan_only
from lattice.runtime import FileAgentEventLog, ScriptGenerationAgent, ScriptRunner
from lattice.schemas import PermissionMode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lattice")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Run the LATTICE planning flow.")
    plan_parser.add_argument("request", help="User request to plan.")
    plan_parser.add_argument("--session-id", default=None)
    plan_parser.add_argument("--event-log", default=None, help="Optional JSONL event log path.")
    plan_parser.add_argument("--config-dir", default="config")
    plan_parser.add_argument("--graph-profile", default=None)

    execute_parser = subparsers.add_parser("execute", help="Run the executable LATTICE agent flow.")
    execute_parser.add_argument("request", help="User request to execute.")
    execute_parser.add_argument("--session-id", default=None)
    execute_parser.add_argument("--event-log", default=None, help="Optional JSONL event log path.")
    execute_parser.add_argument("--config-dir", default="config")
    execute_parser.add_argument("--graph-profile", default=None)
    execute_parser.add_argument("--permission-mode", default="safe_execute")
    execute_parser.add_argument(
        "--skip-experience-write",
        action="store_true",
        help="Build but do not write execution experience GraphPatch to L0.",
    )

    graph_parser = subparsers.add_parser("graph", help="Graph asset operations.")
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command", required=True)
    validate_parser = graph_subparsers.add_parser(
        "validate-assets",
        help="Validate G0/G1 asset directories against the shared six-layer schema.",
    )
    validate_parser.add_argument("--l0-path", required=True)
    validate_parser.add_argument("--l1-path", required=True)

    import_parser = graph_subparsers.add_parser(
        "import-assets",
        help="Import externally built graph assets through the configured graph store.",
    )
    import_parser.add_argument("--config-dir", default="config")
    import_parser.add_argument("--graph-profile", required=True)
    import_parser.add_argument("--tier", choices=["G0", "G1"], required=True)
    import_parser.add_argument("--asset-path", required=True)

    db_parser = subparsers.add_parser("db", help="Database setup helpers.")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)
    init_pg_parser = db_subparsers.add_parser(
        "init-postgres",
        help="Create LATTICE core PostgreSQL tables.",
    )
    init_pg_parser.add_argument("--config-dir", default="config")

    args = parser.parse_args(argv)
    if args.command == "plan":
        event_log = FileAgentEventLog(args.event_log) if args.event_log else None
        healthy_graph_store = None
        if args.graph_profile:
            settings = load_settings(args.config_dir)
            runtime = load_graph_runtime(settings, profile_id=args.graph_profile)
            healthy_graph_store = runtime.l1_store
        state = run_plan_only(
            args.request,
            session_id=args.session_id,
            event_log=event_log,
            healthy_graph_store=cast(HealthyGraphStore | None, healthy_graph_store),
        )
        print(json.dumps(_to_jsonable(state), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "execute":
        settings = load_settings(args.config_dir)
        runtime = load_graph_runtime(settings, profile_id=args.graph_profile)
        event_log = FileAgentEventLog(args.event_log) if args.event_log else None
        state = run_execution(
            args.request,
            session_id=args.session_id,
            event_log=event_log,
            permission_mode=cast(PermissionMode, args.permission_mode),
            healthy_graph_store=cast(HealthyGraphStore | None, runtime.l1_store),
            full_graph_store=cast(FullGraphStore | None, runtime.l0_store),
            apply_experience_patch=not args.skip_experience_write,
            script_generation_agent=ScriptGenerationAgent.from_model_settings(
                settings.models
            ),
            script_runner=ScriptRunner(
                output_root=(
                    Path(settings.runtime_paths.output_root)
                    / settings.runtime_paths.runs_subdir
                )
            ),
        )
        print(json.dumps(_to_jsonable(state), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "graph":
        if args.graph_command == "validate-assets":
            l0_records = load_graph_records(args.l0_path, graph_tier="G0")
            l1_records = load_graph_records(args.l1_path, graph_tier="G1")
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "l0": {"nodes": len(l0_records.nodes), "edges": len(l0_records.edges)},
                        "l1": {"nodes": len(l1_records.nodes), "edges": len(l1_records.edges)},
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.graph_command == "import-assets":
            settings = load_settings(args.config_dir)
            runtime = load_graph_runtime(settings, profile_id=args.graph_profile)
            store = runtime.l0_store if args.tier == "G0" else runtime.l1_store
            if store is None or not hasattr(store, "replace_records"):
                raise GraphRuntimeLoadError(
                    f"Configured {args.tier} store does not support asset import."
                )
            report = GraphAssetImporter().import_records(
                profile=runtime.profile,
                graph_tier=args.tier,
                asset_path=args.asset_path,
                store=cast(GraphRecordStore, store),
            )
            print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
    if args.command == "db" and args.db_command == "init-postgres":
        settings = load_settings(args.config_dir)
        if not settings.databases.postgres_dsn:
            parser.error("databases.postgres_dsn is required.")
        PostgresSchemaManager(dsn=settings.databases.postgres_dsn).create_core_tables()
        print(json.dumps({"status": "initialized"}, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())

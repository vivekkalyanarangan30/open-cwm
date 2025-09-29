from __future__ import annotations

import argparse
import json
from pathlib import Path
from .catalog import RepoCatalog
from .pipeline import PipelineContext, RepoPipeline, Stage


def _load_repo(args: argparse.Namespace) -> RepoPipeline:
    catalog = RepoCatalog.from_file(args.catalog)
    repo = catalog.get(args.repo_id)
    workspace = Path(args.workspace)
    context = PipelineContext(repo=repo, workspace=workspace)
    return RepoPipeline(context)


def cmd_list(args: argparse.Namespace) -> None:
    catalog = RepoCatalog.from_file(args.catalog)
    for repo in catalog.iter_repos():
        print(f"{repo.id}\t{repo.url}\t{repo.commit}")


def cmd_status(args: argparse.Namespace) -> None:
    pipeline = _load_repo(args)
    statuses = pipeline.status()
    print(json.dumps(statuses, indent=2))


def _run_to_stage(args: argparse.Namespace, stage: Stage) -> None:
    pipeline = _load_repo(args)
    result = pipeline.run_until(stage)
    print(json.dumps(result.to_dict(), indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open-CWM Module 1 orchestrator")
    parser.add_argument(
        "--catalog",
        default="repo_catalog/repos.yaml",
        help="Path to the repository catalog file.",
    )
    parser.add_argument(
        "--workspace",
        default=".open-cwm",
        help="Directory used for clones, state, and artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List repositories in the catalog")
    list_parser.set_defaults(func=cmd_list)

    status_parser = subparsers.add_parser("status", help="Show pipeline status for a repo")
    status_parser.add_argument("--repo-id", required=True)
    status_parser.set_defaults(func=cmd_status)

    for command, stage in (
        ("discover", Stage.DISCOVER),
        ("plan", Stage.PLAN),
        ("build", Stage.BUILD),
        ("test", Stage.TEST),
        ("package", Stage.PACKAGE),
        ("publish", Stage.PUBLISH),
    ):
        stage_parser = subparsers.add_parser(command, help=f"Run pipeline stage: {command}")
        stage_parser.add_argument("--repo-id", required=True)
        stage_parser.set_defaults(func=lambda args, stage=stage: _run_to_stage(args, stage))

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()

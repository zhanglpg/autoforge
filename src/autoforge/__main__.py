"""
AutoForge CLI entry point.

Commands:
  run      — Execute a workflow (measure -> act -> validate loop)
  health   — Run all metric adapters and produce a health dashboard
  list     — List available workflows and adapters
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from autoforge import __version__


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    """Execute a workflow."""
    from autoforge.registry import find_workflow_config, get_adapter
    from autoforge.reporting import report_to_markdown, save_run_report
    from autoforge.runner import WorkflowRunner

    # Load workflow config
    if args.config:
        from autoforge.registry import load_workflow_config
        config = load_workflow_config(args.config)
    else:
        config = find_workflow_config(args.workflow)

    # Override budget from CLI
    if args.max_iterations is not None:
        config.budget.max_iterations = args.max_iterations
    if args.max_tokens is not None:
        config.budget.max_tokens = args.max_tokens
    if args.max_time is not None:
        config.budget.max_wall_clock_minutes = args.max_time

    # Get the adapter
    adapter_name = args.adapter or config.adapter or config.name
    adapter = get_adapter(adapter_name)

    # Resolve paths
    repo_path = str(Path(args.repo).resolve())
    target_path = str(Path(args.path).resolve()) if args.path else repo_path

    # Create and run
    runner = WorkflowRunner(
        config=config,
        adapter=adapter,
        repo_path=repo_path,
        target_path=target_path,
        target_value=args.target,
        test_command=args.test_command,
        skip_tests=args.skip_tests,
        skip_git=args.skip_git,
        dry_run=args.dry_run,
        agent_command=args.agent_command,
    )

    report = runner.run()

    # Save report
    output_dir = args.output or str(Path(repo_path) / ".autoforge" / "reports")
    json_path, md_path = save_run_report(report, output_dir)

    # Print summary
    print()
    print(report_to_markdown(report))
    print()
    print(f"Reports saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")

    return 0 if report.outcome.value == "target_met" else 1


def cmd_health(args: argparse.Namespace) -> int:
    """Run health check across all (or specified) adapters."""
    from autoforge.registry import get_adapter, list_adapters
    from autoforge.reporting import format_health_dashboard
    from autoforge.models import MetricResult

    repo_path = str(Path(args.repo).resolve())
    target_path = str(Path(args.path).resolve()) if args.path else repo_path

    adapter_names = args.adapters.split(",") if args.adapters else list_adapters()

    metrics: dict[str, MetricResult] = {}
    for name in adapter_names:
        try:
            adapter = get_adapter(name)
            if adapter.check_prerequisites(repo_path):
                result = adapter.measure(repo_path, target_path)
                metrics[name] = result
            else:
                logging.getLogger(__name__).warning(
                    "Skipping adapter '%s': prerequisites not met", name
                )
        except Exception as e:
            logging.getLogger(__name__).error("Adapter '%s' failed: %s", name, e)

    if not metrics:
        print("No metrics collected. Check adapter prerequisites.")
        return 1

    dashboard = format_health_dashboard(metrics)

    if args.format == "json":
        data = {
            name: {
                "metric_name": r.metric_name,
                "value": r.value,
                "unit": r.unit,
                "direction": r.direction.value,
                "breakdown": r.breakdown,
            }
            for name, r in metrics.items()
        }
        print(json.dumps(data, indent=2))
    else:
        print(dashboard)

    # Save if output specified
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dashboard + "\n")
        print(f"\nSaved to: {out}")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List available workflows and adapters."""
    from autoforge.registry import list_adapters, list_workflows

    print("Available Adapters:")
    for name in list_adapters():
        print(f"  - {name}")

    print()
    print("Available Workflows:")
    workflows = list_workflows()
    if workflows:
        for name in workflows:
            print(f"  - {name}")
    else:
        print("  (none found)")

    return 0


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoforge",
        description="AutoForge: Autonomous metric-driven agentic coding framework",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- run ---
    run_p = subparsers.add_parser("run", help="Execute a workflow")
    run_p.add_argument(
        "workflow",
        help="Workflow name (e.g., 'complexity_refactor') or path to YAML config",
    )
    run_p.add_argument(
        "--path", "-p",
        default=None,
        help="Target path to improve (default: repo root)",
    )
    run_p.add_argument(
        "--repo", "-r",
        default=".",
        help="Repository root (default: current directory)",
    )
    run_p.add_argument(
        "--target", "-t",
        type=float,
        default=None,
        help="Target metric value to achieve",
    )
    run_p.add_argument(
        "--adapter", "-a",
        default=None,
        help="Metric adapter to use (default: inferred from workflow)",
    )
    run_p.add_argument(
        "--config", "-c",
        default=None,
        help="Path to workflow YAML config file",
    )
    run_p.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max iterations",
    )
    run_p.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override max token budget",
    )
    run_p.add_argument(
        "--max-time",
        type=int,
        default=None,
        help="Override max wall-clock time (minutes)",
    )
    run_p.add_argument(
        "--test-command",
        default=None,
        help="Test command to run for regression guard",
    )
    run_p.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test validation between iterations",
    )
    run_p.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip git branch/commit management",
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Measure only, don't run agent",
    )
    run_p.add_argument(
        "--agent-command",
        default=None,
        help="Custom agent command (overrides workflow agent.command; used as-is)",
    )
    run_p.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for reports",
    )
    run_p.set_defaults(func=cmd_run)

    # --- health ---
    health_p = subparsers.add_parser("health", help="Run health check")
    health_p.add_argument(
        "--path", "-p",
        default=None,
        help="Target path to analyze (default: repo root)",
    )
    health_p.add_argument(
        "--repo", "-r",
        default=".",
        help="Repository root (default: current directory)",
    )
    health_p.add_argument(
        "--adapters",
        default=None,
        help="Comma-separated list of adapters to run (default: all)",
    )
    health_p.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    health_p.add_argument(
        "--output", "-o",
        default=None,
        help="Save output to file",
    )
    health_p.set_defaults(func=cmd_health)

    # --- list ---
    list_p = subparsers.add_parser("list", help="List available workflows and adapters")
    list_p.set_defaults(func=cmd_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    _setup_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(1)

    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

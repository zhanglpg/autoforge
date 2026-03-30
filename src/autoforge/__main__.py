"""
AutoForge CLI entry point.

Commands:
  run        — Execute a workflow (measure -> act -> validate loop)
  measure    — Run a metric adapter and output results (for skill mode)
  targets    — Identify worst files for a metric (for skill mode)
  skill-info — Generate a skill description from a workflow config
  health     — Run all metric adapters and produce a health dashboard
  list       — List available workflows and adapters
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


def cmd_measure(args: argparse.Namespace) -> int:
    """Run a single metric adapter and output the result."""
    from autoforge.registry import get_adapter

    repo_path = str(Path(args.repo).resolve())
    target_path = str(Path(args.path).resolve()) if args.path else repo_path

    try:
        adapter = get_adapter(args.adapter)
    except ValueError as e:
        print(
            json.dumps({"error": str(e)})
            if args.format == "json"
            else f"Error: {e}"
        )
        return 1

    if not adapter.check_prerequisites(repo_path):
        print(
            json.dumps({"error": f"Prerequisites not met for adapter '{args.adapter}'"})
            if args.format == "json"
            else f"Error: Prerequisites not met for adapter '{args.adapter}'"
        )
        return 1

    result = adapter.measure(repo_path, target_path)

    if args.format == "json":
        data = {
            "metric_name": result.metric_name,
            "value": result.value,
            "unit": result.unit,
            "direction": result.direction.value,
            "breakdown": result.breakdown,
            "tool": result.tool,
            "timestamp": result.timestamp,
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"{result.metric_name}: {result.value} {result.unit} ({result.direction.value})")
        if result.breakdown:
            print(f"\nBreakdown ({len(result.breakdown)} files):")
            sorted_files = sorted(
                result.breakdown.items(),
                key=lambda kv: kv[1],
                reverse=(result.direction.value == "minimize"),
            )
            for path, value in sorted_files[:20]:
                print(f"  {value:8.2f}  {path}")
            if len(result.breakdown) > 20:
                print(f"  ... and {len(result.breakdown) - 20} more files")

    return 0


def cmd_targets(args: argparse.Namespace) -> int:
    """Identify the worst files for a metric adapter."""
    from autoforge.registry import get_adapter

    repo_path = str(Path(args.repo).resolve())
    target_path = str(Path(args.path).resolve()) if args.path else repo_path

    try:
        adapter = get_adapter(args.adapter)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if not adapter.check_prerequisites(repo_path):
        print(f"Error: Prerequisites not met for adapter '{args.adapter}'")
        return 1

    result = adapter.measure(repo_path, target_path)
    targets = adapter.identify_targets(result, args.n)

    if args.format == "json":
        data = {
            "metric_name": result.metric_name,
            "current_value": result.value,
            "direction": result.direction.value,
            "targets": targets,
            "target_scores": {t: result.breakdown.get(t, 0.0) for t in targets},
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Top {len(targets)} targets for {result.metric_name} "
              f"(current: {result.value:.2f}, {result.direction.value}):\n")
        for i, t in enumerate(targets, 1):
            score = result.breakdown.get(t, 0.0)
            print(f"  {i}. {t} ({score:.2f})")

    return 0


def cmd_skill_info(args: argparse.Namespace) -> int:
    """Generate a skill description from a workflow config."""
    from autoforge.registry import find_workflow_config, load_workflow_config
    from autoforge.skill import generate_skill_description, generate_skill_json

    if args.config:
        config = load_workflow_config(args.config)
    else:
        config = find_workflow_config(args.workflow)

    repo_path = str(Path(args.repo).resolve())
    target_path = str(Path(args.path).resolve()) if args.path else repo_path

    kwargs = dict(
        repo_path=repo_path,
        target_path=target_path,
        target_value=args.target,
    )

    if args.format == "json":
        output = generate_skill_json(config, **kwargs)
    else:
        output = generate_skill_description(config, **kwargs)

    print(output)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output + "\n")
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
        description="AutoForge: Metric-driven coding tools for AI agents",
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

    # --- measure ---
    measure_p = subparsers.add_parser(
        "measure",
        help="Run a metric adapter and output results (for skill mode)",
    )
    measure_p.add_argument(
        "adapter",
        help="Adapter name (e.g., 'complexity', 'test_quality')",
    )
    measure_p.add_argument(
        "--path", "-p",
        default=None,
        help="Target path to measure (default: repo root)",
    )
    measure_p.add_argument(
        "--repo", "-r",
        default=".",
        help="Repository root (default: current directory)",
    )
    measure_p.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="json",
        help="Output format (default: json)",
    )
    measure_p.set_defaults(func=cmd_measure)

    # --- targets ---
    targets_p = subparsers.add_parser(
        "targets",
        help="Identify worst files for a metric (for skill mode)",
    )
    targets_p.add_argument(
        "adapter",
        help="Adapter name (e.g., 'complexity', 'test_quality')",
    )
    targets_p.add_argument(
        "--path", "-p",
        default=None,
        help="Target path to analyze (default: repo root)",
    )
    targets_p.add_argument(
        "--repo", "-r",
        default=".",
        help="Repository root (default: current directory)",
    )
    targets_p.add_argument(
        "-n",
        type=int,
        default=5,
        help="Number of target files to return (default: 5)",
    )
    targets_p.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="json",
        help="Output format (default: json)",
    )
    targets_p.set_defaults(func=cmd_targets)

    # --- skill-info ---
    skill_p = subparsers.add_parser(
        "skill-info",
        help="Generate a skill description from a workflow config",
    )
    skill_p.add_argument(
        "workflow",
        help="Workflow name (e.g., 'complexity_refactor')",
    )
    skill_p.add_argument(
        "--path", "-p",
        default=None,
        help="Target path for skill description (default: repo root)",
    )
    skill_p.add_argument(
        "--repo", "-r",
        default=".",
        help="Repository root (default: current directory)",
    )
    skill_p.add_argument(
        "--target", "-t",
        type=float,
        default=None,
        help="Target metric value",
    )
    skill_p.add_argument(
        "--config", "-c",
        default=None,
        help="Path to workflow YAML config file",
    )
    skill_p.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text/markdown)",
    )
    skill_p.add_argument(
        "--output", "-o",
        default=None,
        help="Save output to file",
    )
    skill_p.set_defaults(func=cmd_skill_info)

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

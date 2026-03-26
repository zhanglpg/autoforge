# AutoForge — Development Progress

## Completed

### Core Framework
- [x] CLI entry point with three commands: `run`, `health`, `list`
- [x] YAML-based workflow configuration system (`WorkflowConfig`, `BudgetConfig`)
- [x] Core data models: `MetricResult`, `RunReport`, `IterationRecord`, `RunOutcome`, `Direction`
- [x] Adapter registry with dynamic registration and workflow discovery

### Iteration Engine
- [x] `WorkflowRunner` — full measure → act → validate → commit loop
- [x] Subprocess-based agent invocation (default: Claude Code)
- [x] Custom agent command support (`--agent-command`)
- [x] Dry-run mode (measure only, no agent)
- [x] Token usage parsing from agent JSON output and stderr

### Budget Management
- [x] `BudgetManager` — iteration, token, and wall-clock time limits
- [x] Stall detection (configurable patience and minimum improvement threshold)
- [x] Early termination on budget exhaustion or stall

### Git Integration
- [x] `GitManager` — automatic branch creation per workflow run (timestamped)
- [x] Per-iteration commits with metric deltas in messages
- [x] Rollback on failed iterations (`git reset --hard`)
- [x] Modified file tracking

### Regression Guard
- [x] `RegressionGuard` — test suite execution between iterations
- [x] Auto-detection of test commands (pytest, npm, go, cargo)
- [x] Constraint metric validation with configurable tolerance
- [x] Rollback on test failure or constraint violation

### Reporting
- [x] JSON and Markdown run report generation
- [x] Health dashboard with per-adapter status indicators
- [x] Report saving to output directory

### Adapters
- [x] `BaseMetricAdapter` abstract base class with shared utilities
- [x] `ComplexityAdapter` — NCS measurement via `complexity-accounting`
  - Supported languages: Python, Go, Java, JavaScript, TypeScript, Rust, C++
  - Per-file cognitive complexity breakdown
  - Priority file targeting (highest complexity first)
- [x] `TestQualityAdapter` — composite Test Quality Score (TQS, 0–100)
  - Coverage sub-metric (line + branch, 30% weight)
  - Function coverage gap analysis (20% weight)
  - Assertion quality scoring with strength classification (30% weight)
  - Optional mutation testing via mutmut (20% weight)
  - Per-file TQS breakdown

### Workflows
- [x] `complexity_refactor.yaml` — reduce NCS with complexity-focused agent prompts
- [x] `test_quality.yaml` — improve TQS with test-generation agent prompts

### Testing
- [x] Comprehensive test suite (~4,400 lines across 14 test files)
- [x] CI pipeline: pytest on Python 3.10–3.13, coverage on 3.12

### Documentation
- [x] README with full CLI reference, architecture diagram, and adapter guide

## Next Steps
- [ ] Additional metric adapters (e.g., security, documentation coverage, performance)
- [ ] Parallel adapter execution in health checks
- [ ] Web dashboard for run history and trend visualization
- [ ] Plugin system for third-party adapters (entry points)
- [ ] Multi-workflow orchestration (run several workflows in sequence)

Improve Python test quality in this project using AutoForge metrics.

## Tool Setup

Run the following to get the metric contract (commands, budget, constraints):

```
autoforge skill-info test_quality --path $ARGUMENTS --target 80.0
```

If no path argument was provided, use `./src` as the default path.

Use `autoforge measure test_quality` and `autoforge targets test_quality` as your
measurement tools throughout the workflow.

## Iteration Protocol

Each iteration:
1. Run `autoforge measure test_quality` to get current TQS
2. Run `autoforge targets test_quality` to find worst-tested files
3. Read the target source files to understand what needs testing
4. Write or improve tests -- each test function needs at least one assertion
5. Run tests to verify they pass
6. Re-measure to confirm TQS improved
7. Commit with a descriptive message

## Guidelines

- Make focused, minimal changes per iteration
- Each test function MUST have at least one assertion on the output
- One assertion per test is sufficient; do NOT add extra assertions just to pad
- Cover distinct code paths: edge cases, error paths, boundary values
- Prefer testing behaviour over implementation details
- Always measure before and after to confirm improvement
- If stuck or the metric isn't improving, try a fundamentally different approach
- Stop when target is met or budget is exhausted

## Getting Started

1. Run the skill-info command above to see the metric contract and budget
2. Run the measure command to get the baseline
3. Run the targets command to see which files need the most work
4. Start your first iteration

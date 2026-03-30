Improve Go test quality in this project using AutoForge metrics.

## Tool Setup

Run the following to get the metric contract (commands, budget, constraints):

```
autoforge skill-info go_test_quality --path $ARGUMENTS --target 80.0
```

If no path argument was provided, use `.` as the default path.

Use `autoforge measure go_test_quality` and `autoforge targets go_test_quality` as your
measurement tools throughout the workflow.

## Iteration Protocol

Each iteration:
1. Run `autoforge measure go_test_quality` to get current TQS
2. Run `autoforge targets go_test_quality` to find worst-tested files
3. Read the target source files to understand what needs testing
4. Write or improve tests -- use table-driven tests, subtests, explicit assertions
5. Run `go test ./...` to verify they pass
6. Re-measure to confirm TQS improved
7. Commit with a descriptive message

## Guidelines

- Make focused, minimal changes per iteration
- Each test function MUST have at least one assertion (explicit comparison or testify)
- Prefer table-driven tests for functions with multiple input scenarios
- Use t.Run for subtests to organize test cases
- Test error paths: check that functions return expected errors
- Cover distinct code paths: edge cases, error paths, boundary values
- Follow Go testing conventions: TestFunctionName, _test.go in same package
- Do NOT add assertions just to pad -- quality over quantity
- Always measure before and after to confirm improvement
- If stuck or the metric isn't improving, try a fundamentally different approach
- Stop when target is met or budget is exhausted

## Getting Started

1. Run the skill-info command above to see the metric contract and budget
2. Run the measure command to get the baseline
3. Run the targets command to see which files need the most work
4. Start your first iteration

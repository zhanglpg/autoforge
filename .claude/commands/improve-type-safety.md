Improve type safety in this project using AutoForge metrics.

## Tool Setup

Run the following to get the metric contract (commands, budget, constraints):

```
autoforge skill-info type_safety --path $ARGUMENTS --target 0
```

If no path argument was provided, use `./src` as the default path.

Use `autoforge measure type_safety` and `autoforge targets type_safety` as your
measurement tools throughout the workflow.

## Iteration Protocol

Each iteration:
1. Run `autoforge measure type_safety` to get current type error count
2. Run `autoforge targets type_safety` to find files with most type errors
3. Read the target files and understand the specific type errors
4. Add type annotations and fix type errors
5. Run tests to verify no regressions
6. Re-measure to confirm error count decreased
7. Commit with a descriptive message

## Guidelines

- Make focused, minimal changes per iteration (fix errors in 2-4 files)
- Add type annotations to function signatures first, then fix type errors
- Prefer precise types over `Any` -- use `Any` only as a last resort
- Do NOT change runtime behavior unless fixing a genuine type bug
- Use typing constructs: Optional, Union, TypeVar, Protocol, Literal, etc.
- For third-party libraries without stubs, use `type: ignore` with specific codes
- Always measure before and after to confirm improvement
- If stuck or the metric isn't improving, try a fundamentally different approach
- Stop when target is met or budget is exhausted

## Getting Started

1. Run the skill-info command above to see the metric contract and budget
2. Run the measure command to get the baseline
3. Run the targets command to see which files need the most work
4. Start your first iteration

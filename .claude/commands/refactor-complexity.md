Reduce code complexity in this project using AutoForge metrics.

## Tool Setup

Run the following to get the metric contract (commands, budget, constraints):

```
autoforge skill-info complexity_refactor --path $ARGUMENTS --target 3.0
```

If no path argument was provided, use `./src` as the default path.

Use `autoforge measure complexity` and `autoforge targets complexity` as your
measurement tools throughout the workflow.

## Iteration Protocol

Each iteration:
1. Run `autoforge measure complexity` to get current NCS
2. Run `autoforge targets complexity` to find worst files
3. Read the target files and identify complexity hotspots
4. Make 2-4 focused refactorings (extract functions, reduce nesting, simplify dispatch)
5. Run tests to verify no regressions
6. Re-measure to confirm NCS improved
7. Commit with a descriptive message

## Guidelines

- Make focused, minimal changes per iteration (2-4 related refactorings)
- Preserve existing behavior -- these are pure refactorings with no feature additions
- Always measure before and after to confirm improvement
- If stuck or the metric isn't improving, try a fundamentally different approach
- Stop when target is met or budget is exhausted

## Getting Started

1. Run the skill-info command above to see the metric contract and budget
2. Run the measure command to get the baseline
3. Run the targets command to see which files need the most work
4. Start your first iteration

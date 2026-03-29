Reduce code complexity in this project using AutoForge metrics.

First, generate the skill description by running:

```
autoforge skill-info complexity_refactor --path $ARGUMENTS --target 3.0
```

If no path argument was provided, use `./src` as the default path.

Follow the skill description output exactly. It contains the full iteration protocol:
measure, identify targets, make changes, run tests, re-measure, and commit.

Use `autoforge measure complexity` and `autoforge targets complexity` as your
measurement tools throughout the workflow.

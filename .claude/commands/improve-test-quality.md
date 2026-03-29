Improve Python test quality in this project using AutoForge metrics.

First, generate the skill description by running:

```
autoforge skill-info test_quality --path $ARGUMENTS --target 80.0
```

If no path argument was provided, use `./src` as the default path.

Follow the skill description output exactly. It contains the full iteration protocol:
measure, identify targets, write tests, run tests, re-measure, and commit.

Use `autoforge measure test_quality` and `autoforge targets test_quality` as your
measurement tools throughout the workflow.

Improve Go test quality in this project using AutoForge metrics.

First, generate the skill description by running:

```
autoforge skill-info go_test_quality --path $ARGUMENTS --target 80.0
```

If no path argument was provided, use `.` as the default path.

Follow the skill description output exactly. It contains the full iteration protocol:
measure, identify targets, write tests, run tests, re-measure, and commit.

Use `autoforge measure go_test_quality` and `autoforge targets go_test_quality` as your
measurement tools throughout the workflow.

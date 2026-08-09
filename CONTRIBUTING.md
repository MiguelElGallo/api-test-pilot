# Contributing

Use Python 3.12 or later and install a wheel-equivalent environment with
`uv sync --all-extras --no-editable`.

Every Python module, public class, public function, test, and test double must have a useful
docstring. Keep contract parsing, generation strategies, execution, reporting, and external adapters
in their existing cohesive modules. New behavior requires focused unit coverage and, where
applicable, an end-to-end generated regression test.

Before opening a pull request, run:

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync pytest
```

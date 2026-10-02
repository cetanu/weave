# Weave

A Rust-backed Python library for merging nested dictionaries. One function,
no runtime Python dependencies, and no mutation of your inputs.

Install from this checkout with `python -m pip install .` (requires Rust).
The extension uses [PyO3](https://pyo3.rs/) and is built with
[maturin](https://www.maturin.rs/).

```python
from weave import merge

defaults = {"server": {"host": "localhost", "port": 8000}, "plugins": ["logging"]}
overrides = {"server": {"port": 9000}, "plugins": ["metrics"]}

merge(defaults, overrides)
# {"server": {"host": "localhost", "port": 9000}, "plugins": ["metrics"]}

merge(defaults, overrides, concat_lists=True)
# {"server": {"host": "localhost", "port": 9000}, "plugins": ["logging", "metrics"]}
```

## Merge semantics

`merge(left, right, *, concat_lists=False) -> dict`

- Both arguments must be dictionaries (subclasses are accepted).
- When both values at a key are dictionaries, merge them recursively.
- Otherwise the right value replaces the left, including `None` and empty values.
- With `concat_lists=True`, two lists concatenate in left-to-right order at
  every dictionary depth. Duplicates remain; elements are not merged by index.
- Every dictionary and list reached through dictionary values or list elements
  is copied. Changing those containers in the result does not change either input.
  Container subclasses become plain dictionaries and lists, using their stored
  contents rather than overridden Python methods.
- Keys and other objects (including tuples, sets, and custom instances) retain
  their identity. Weave does not traverse them or call `__deepcopy__`.
  For example, a list inside an opaque tuple remains shared.
- Repeated references to the same container are copied separately; alias
  relationships are not preserved.
- Existing keys retain their left-hand insertion order. New keys are appended
  in right-hand order. All hashable Python keys are supported.
- Traversed cycles or more than 256 nested dictionary/list levels raise
  `RecursionError`; Python's own stack guard can stop traversal earlier.
  Overwritten values are not traversed.
- Exceptions from key hashing or equality propagate. Inputs must not be mutated
  during a merge, including from key callbacks.

## Development

Requires CPython 3.11+ and Rust 1.85+ to build from source. Native wheels do not
require Rust. The extension uses the full Python API for performance, so wheels
are specific to a Python version. It holds the GIL while accessing Python objects.

```sh
uv sync
uv run pytest
uv run ruff check .
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```

`uv sync` builds the extension in release mode. After editing Rust, rebuild it
with `uv run maturin develop --release` before testing. Build distribution
artifacts with `uv run maturin build --release` and `uv run maturin sdist`.

## Performance

The merge walks Python containers directly through PyO3, with native dictionary
copies and list concatenation. Scalar leaves stay as Python objects; there is no
JSON encoding, deserialization, or conversion to Rust maps.

Run the Airspeed Velocity benchmarks against an equivalent Python implementation:

```sh
uv sync
uv run asv continuous --factor 1.15 --interleave-rounds --split HEAD^ HEAD
```

Benchmarks check matching results before timing and cover flat dictionaries,
nested configuration, deep dictionaries, large lists, and list concatenation.
Both implementations copy dict/list containers and share opaque leaves. ASV
stores results in `.asv/results`; CI compares each pull request against its base
revision on the same runner and uploads the result files as a workflow artifact.
The 15% threshold filters small variations. Use release builds and measure your
own workload; Python allocation and key hashing still determine much of the cost.

See [local benchmark results](benchmarks/README.md) for measured timings and
the machine and sampling conditions.

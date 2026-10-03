from dataclasses import dataclass

from weave import merge


@dataclass
class BenchCase:
    name: str
    source: dict
    dest: dict

    def __call__(self):
        return self.source, self.dest, self.name in CONCAT_LIST_CASES


CONCAT_LIST_CASES = {"nested_concat", "list_concat", "container_lists"}


def copy_value(value):
    if isinstance(value, dict):
        return {key: copy_value(child) for key, child in dict.items(value)}
    if isinstance(value, list):
        return [copy_value(child) for child in list.__iter__(value)]
    return value


def python_merge(left, right, *, concat_lists=False):
    result = dict.copy(left)
    for key, value in dict.items(left):
        if isinstance(value, (dict, list)) and key not in right:
            result[key] = copy_value(value)
    for key, value in dict.items(right):
        previous = dict.get(left, key)
        if isinstance(previous, dict) and isinstance(value, dict):
            result[key] = python_merge(previous, value, concat_lists=concat_lists)
        elif concat_lists and isinstance(previous, list) and isinstance(value, list):
            result[key] = copy_value(list.__add__(previous, value))
        else:
            result[key] = copy_value(value)
    return result


def cases():
    nested_left = {
        f"service{i}": {
            "host": "localhost",
            "port": 8000 + i,
            "tls": {"enabled": False},
            "plugins": ["logging", "auth"],
        }
        for i in range(100)
    }
    nested_right = {
        f"service{i}": {"tls": {"enabled": True}, "plugins": ["metrics"]} for i in range(100)
    }
    deep_source, deep_dest = {"left": 1}, {"right": 2}
    for _ in range(100):
        deep_source, deep_dest = {"child": deep_source}, {"child": deep_dest}
    overwritten = {
        f"service{i}": {
            "host": "localhost",
            "port": 8000 + i,
            "tls": {"enabled": False},
            "plugins": ["logging", "auth"],
        }
        for i in range(100)
    }
    wide_left = {f"key{i}": i for i in range(10_000)}
    wide_right = {f"key{i}": -i for i in range(10_000)}
    wide_left["key9999"] = {"before": [1]}
    wide_right["key9999"] = {"after": [2]}
    medium_left = {f"key{i}": i for i in range(32)}
    medium_right = {f"other{i}": -i for i in range(32)}
    copied_subtree = {f"key{i}": i for i in range(10_000)}
    return [
        BenchCase("tiny", {"a": 1, "b": 2}, {"b": 3, "c": 4}),
        BenchCase(
            "flat",
            {f"k{i}": i for i in range(10_000)},
            {f"k{i}": -i for i in range(5_000, 15_000)},
        ),
        BenchCase("nested", nested_left, nested_right),
        BenchCase("nested_concat", nested_left, nested_right),
        BenchCase("deep", deep_source, deep_dest),
        BenchCase("list_replace", {"items": list(range(10_000))}, {"items": list(range(10_000))}),
        BenchCase("list_concat", {"items": list(range(10_000))}, {"items": list(range(10_000))}),
        BenchCase(
            "container_lists",
            {"items": [{"id": i, "tags": [i]} for i in range(500)]},
            {"items": [{"id": i, "tags": [i]} for i in range(500, 1_000)]},
        ),
        BenchCase("overwritten", {"items": overwritten}, {"items": None}),
        BenchCase("wide_mixed_late", wide_left, wide_right),
        BenchCase("medium", medium_left, medium_right),
        BenchCase("copy_subtree", {}, {"config": copied_subtree}),
    ]


class MergeBenchmarks:
    def setup(self):
        self.workloads = {case.name: case() for case in cases()}
        for name, (left, right, concat_lists) in self.workloads.items():
            assert merge(left, right, concat_lists=concat_lists) == python_merge(
                left, right, concat_lists=concat_lists
            ), name

    def _run(self, workload, implementation):
        left, right, concat_lists = self.workloads[workload]
        function = merge if implementation == "weave" else python_merge
        return function(left, right, concat_lists=concat_lists)

    def time_tiny_weave(self):
        self._run("tiny", "weave")

    def time_tiny_python(self):
        self._run("tiny", "python")

    def time_flat_weave(self):
        self._run("flat", "weave")

    def time_flat_python(self):
        self._run("flat", "python")

    def time_nested_weave(self):
        self._run("nested", "weave")

    def time_nested_python(self):
        self._run("nested", "python")

    def time_nested_concat_weave(self):
        self._run("nested_concat", "weave")

    def time_nested_concat_python(self):
        self._run("nested_concat", "python")

    def time_deep_weave(self):
        self._run("deep", "weave")

    def time_deep_python(self):
        self._run("deep", "python")

    def time_list_replace_weave(self):
        self._run("list_replace", "weave")

    def time_list_replace_python(self):
        self._run("list_replace", "python")

    def time_list_concat_weave(self):
        self._run("list_concat", "weave")

    def time_list_concat_python(self):
        self._run("list_concat", "python")

    def time_container_lists_weave(self):
        self._run("container_lists", "weave")

    def time_container_lists_python(self):
        self._run("container_lists", "python")

    def time_overwritten_weave(self):
        self._run("overwritten", "weave")

    def time_overwritten_python(self):
        self._run("overwritten", "python")

    def time_wide_mixed_late_weave(self):
        self._run("wide_mixed_late", "weave")

    def time_wide_mixed_late_python(self):
        self._run("wide_mixed_late", "python")

    def time_medium_weave(self):
        self._run("medium", "weave")

    def time_medium_python(self):
        self._run("medium", "python")

    def time_copy_subtree_weave(self):
        self._run("copy_subtree", "weave")

    def time_copy_subtree_python(self):
        self._run("copy_subtree", "python")

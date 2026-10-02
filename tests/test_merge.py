import inspect
from collections import UserDict

import pytest
from weave import merge


def test_nested_merge():
    left = {"server": {"host": "localhost", "tls": {"enabled": False}}, "keep": 1}
    right = {"server": {"port": 9000, "tls": {"enabled": True}}, "new": 2}
    assert merge(left, right) == {
        "server": {"host": "localhost", "port": 9000, "tls": {"enabled": True}},
        "keep": 1,
        "new": 2,
    }


@pytest.mark.parametrize("left,right", [({}, {}), ({"a": 1}, {}), ({}, {"a": 1})])
def test_empty_inputs(left, right):
    result = merge(left, right)
    assert result == left | right
    assert result is not left
    assert result is not right


@pytest.mark.parametrize("concat_lists", [False, True])
@pytest.mark.parametrize(
    "left,right,expected",
    [
        ({"x": 1}, {"x": 2}, {"x": 2}),
        ({"x": {"a": 1}}, {"x": None}, {"x": None}),
        ({"x": [1]}, {"x": {"a": 2}}, {"x": {"a": 2}}),
        ({"x": {"a": 1}}, {"x": [2]}, {"x": [2]}),
        ({"x": 1}, {"x": {}}, {"x": {}}),
        ({"x": {"a": 1}}, {"x": {}}, {"x": {"a": 1}}),
        ({"x": 1}, {"x": False}, {"x": False}),
        ({"x": 1}, {"x": ""}, {"x": ""}),
        ({"x": (1,)}, {"x": (2,)}, {"x": (2,)}),
        ({"x": {1}}, {"x": {2}}, {"x": {2}}),
    ],
)
def test_conflicts(left, right, expected, concat_lists):
    assert merge(left, right, concat_lists=concat_lists) == expected


def test_lists_replace_by_default_and_concatenate_at_every_dict_depth():
    left = {"x": [1, 1], "nested": {"y": [2], "z": []}}
    right = {"x": [1, 3], "nested": {"y": [], "z": [4]}}
    assert merge(left, right) == right
    assert merge(left, right, concat_lists=True) == {
        "x": [1, 1, 1, 3],
        "nested": {"y": [2], "z": [4]},
    }


def test_list_elements_are_not_merged_by_index():
    left = {"x": [{"a": 1}, [1]]}
    right = {"x": [{"b": 2}, [2]]}
    assert merge(left, right, concat_lists=True) == {"x": [{"a": 1}, [1], {"b": 2}, [2]]}


@pytest.mark.parametrize("concat_lists", [False, True])
def test_all_surviving_containers_are_independent(concat_lists):
    left = {
        "untouched": {"items": [{"values": [1]}]},
        "merged": {"left": [2]},
        "conflict": [{"values": [3]}],
    }
    right = {
        "added": [{"values": [4]}],
        "merged": {"right": [5]},
        "conflict": [{"values": [6]}],
    }
    result = merge(left, right, concat_lists=concat_lists)
    result["untouched"]["items"][0]["values"].append(7)
    result["merged"]["left"].append(8)
    result["merged"]["right"].append(9)
    result["added"][0]["values"].append(10)
    for item in result["conflict"]:
        item["values"].clear()
    assert left == {
        "untouched": {"items": [{"values": [1]}]},
        "merged": {"left": [2]},
        "conflict": [{"values": [3]}],
    }
    assert right == {
        "added": [{"values": [4]}],
        "merged": {"right": [5]},
        "conflict": [{"values": [6]}],
    }


def test_arbitrary_leaves_and_keys_preserve_identity():
    class Leaf:
        def __deepcopy__(self, memo):
            raise AssertionError("must not invoke deepcopy")

    key, leaf = object(), Leaf()
    opaque_tuple, opaque_set = ([1],), {1}
    left = {key: leaf, "tuple": opaque_tuple, "set": opaque_set, 1: "old"}
    result = merge(left, {True: "new", ("tuple", 2): b"bytes", None: 10**100, "π": "雪"})
    assert next(iter(result)) is key
    assert result[key] is leaf
    assert result["tuple"] is opaque_tuple
    assert result["set"] is opaque_set
    assert result[1] == "new"
    assert result[None] == 10**100
    assert result["π"] == "雪"


def test_order_and_equal_key_identity():
    class Key:
        def __init__(self, name):
            self.name = name

        def __hash__(self):
            return hash(self.name)

        def __eq__(self, other):
            return isinstance(other, Key) and self.name == other.name

    left_key, right_key = Key("same"), Key("same")
    result = merge(
        {"first": 1, left_key: {"a": 1}, "last": 3},
        {"new": 4, right_key: {"b": 2}, "first": 5},
    )
    assert list(result) == ["first", left_key, "last", "new"]
    assert list(result)[1] is left_key
    assert result[left_key] == {"a": 1, "b": 2}


def test_container_subclasses_use_stored_contents():
    class DictSubclass(dict):
        def items(self):
            raise AssertionError("must use stored dictionary entries")

        def copy(self):
            raise AssertionError("must use native dictionary copying")

        def __getitem__(self, key):
            raise AssertionError("must use native dictionary lookup")

    class ListSubclass(list):
        def __iter__(self):
            raise AssertionError("must use stored list elements")

        def __add__(self, other):
            raise AssertionError("must use native list concatenation")

        def __getitem__(self, key):
            raise AssertionError("must use native list access")

    left = DictSubclass(x=DictSubclass(a=1), items=ListSubclass([DictSubclass(a=1)]))
    right = DictSubclass(x=DictSubclass(b=2), items=ListSubclass([ListSubclass([2])]))
    result = merge(left, right, concat_lists=True)
    assert result == {"x": {"a": 1, "b": 2}, "items": [{"a": 1}, [2]]}
    assert type(result) is dict
    assert type(result["x"]) is dict
    assert type(result["items"]) is list
    assert type(result["items"][0]) is dict
    assert type(result["items"][1]) is list


@pytest.mark.parametrize("concat_lists", [False, True])
def test_same_input_is_safe(concat_lists):
    source = {"nested": {"items": [{"a": 1}]}}
    result = merge(source, source, concat_lists=concat_lists)
    count = 2 if concat_lists else 1
    assert result == {"nested": {"items": [{"a": 1}] * count}}
    result["nested"]["items"][0]["a"] = 2
    assert source == {"nested": {"items": [{"a": 1}]}}
    if concat_lists:
        assert result["nested"]["items"][1] == {"a": 1}


def test_shared_containers_are_copied_per_occurrence():
    shared = {"items": [1]}
    result = merge({"a": shared}, {"b": shared})
    result["a"]["items"].append(2)
    assert result["b"]["items"] == [1]
    assert shared == {"items": [1]}


@pytest.mark.parametrize("invalid", [None, [], (), "dict", 1, UserDict(a=1)])
def test_requires_dict_arguments(invalid):
    with pytest.raises(TypeError):
        merge(invalid, {})
    with pytest.raises(TypeError):
        merge({}, invalid)


def test_keyword_only_options_and_inspectable_signature():
    with pytest.raises(TypeError):
        merge({}, {}, True)
    with pytest.raises(TypeError):
        merge({}, {}, unknown=True)
    signature = inspect.signature(merge)
    assert list(signature.parameters) == ["left", "right", "concat_lists"]
    assert signature.parameters["concat_lists"].kind == inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["concat_lists"].default is False
    assert merge(left={"a": 1}, right={"b": 2}) == {"a": 1, "b": 2}


@pytest.mark.parametrize("concat_lists", [False, True])
@pytest.mark.parametrize("kind", ["dict", "list", "mixed"])
@pytest.mark.parametrize("side", ["left", "right", "both"])
def test_cycles_raise_and_subsequent_merges_work(concat_lists, kind, side):
    if kind == "dict":
        cyclic = {}
        cyclic["self"] = cyclic
    elif kind == "list":
        cyclic = []
        cyclic.append(cyclic)
    else:
        cyclic = {"items": []}
        cyclic["items"].append(cyclic)
    left = {"x": cyclic} if side in ("left", "both") else {}
    right = {"x": cyclic} if side in ("right", "both") else {}
    with pytest.raises(RecursionError):
        merge(left, right, concat_lists=concat_lists)
    assert merge({"x": {"a": 1}}, {"x": {"b": 2}}) == {"x": {"a": 1, "b": 2}}


def test_overwritten_cycles_are_not_traversed():
    cycle = {}
    cycle["self"] = cycle
    assert merge({"x": cycle}, {"x": 1}) == {"x": 1}


@pytest.mark.parametrize("side", ["left", "right", "both"])
def test_depth_guard(side):
    tree = {"leaf": 1}
    for _ in range(300):
        tree = {"child": tree}
    left = tree if side in ("left", "both") else {}
    right = tree if side in ("right", "both") else {}
    with pytest.raises(RecursionError):
        merge(left, right)


def test_256_container_levels_can_be_copied_and_merged():
    tree = {"leaf": 1}
    for _ in range(255):
        tree = {"child": tree}
    for left, right in ((tree, {}), ({}, tree), (tree, tree)):
        result = merge(left, right)
        for _ in range(255):
            result = result["child"]
        assert result == {"leaf": 1}


def test_hashing_errors_propagate_without_changing_inputs():
    class Key:
        broken = False

        def __hash__(self):
            if self.broken:
                raise ValueError("broken hash")
            return 0

    key = Key()
    left, right = {}, {key: {"items": [1]}}
    key.broken = True
    with pytest.raises(ValueError, match="broken hash"):
        merge(left, right)
    key.broken = False
    assert left == {}
    assert right[key] == {"items": [1]}


def test_equality_errors_propagate_without_changing_inputs():
    class Key:
        def __hash__(self):
            return 0

        def __eq__(self, other):
            raise ValueError("broken equality")

    first, second = Key(), Key()
    left, right = {first: {"a": 1}}, {second: {"b": 2}}
    with pytest.raises(ValueError, match="broken equality"):
        merge(left, right)
    assert left[first] == {"a": 1}
    assert right[second] == {"b": 2}

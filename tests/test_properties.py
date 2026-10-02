from copy import deepcopy

from hypothesis import given, settings
from hypothesis import strategies as st
from weave import merge

keys = st.one_of(st.text(max_size=10), st.integers(), st.none())
leaves = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), st.text(), st.binary())
values = st.recursive(
    leaves,
    lambda children: st.one_of(
        st.lists(children, max_size=5), st.dictionaries(keys, children, max_size=5)
    ),
    max_leaves=40,
)
dicts = st.dictionaries(keys, values, max_size=8)


def reference_merge(left, right, concat_lists):
    """An intentionally straightforward oracle for acyclic built-in values."""
    result = deepcopy(left)
    for key, value in right.items():
        previous = left.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            result[key] = reference_merge(previous, value, concat_lists)
        elif concat_lists and isinstance(previous, list) and isinstance(value, list):
            result[key] = deepcopy(previous + value)
        else:
            result[key] = deepcopy(value)
    return result


@settings(max_examples=300)
@given(left=dicts, right=dicts, concat_lists=st.booleans())
def test_matches_reference_and_preserves_input_container_identities(left, right, concat_lists):
    expected = reference_merge(left, right, concat_lists)
    left_before, right_before = deepcopy(left), deepcopy(right)
    left_ids = container_ids(left)
    right_ids = container_ids(right)
    result = merge(left, right, concat_lists=concat_lists)
    assert equivalent(result, expected)
    assert container_ids(result).isdisjoint(left_ids | right_ids)
    assert container_ids(left) == left_ids
    assert container_ids(right) == right_ids
    assert equivalent(left, left_before)
    assert equivalent(right, right_before)
    assert equivalent(left, merge(left, {}))
    assert equivalent(right, merge({}, right))


def container_ids(value):
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return set()
    result = {id(value)}
    for child in children:
        result.update(container_ids(child))
    return result


def equivalent(left, right):
    # NaN is a valid opaque leaf even though it is not equal to itself.
    if left is right:
        return True
    if isinstance(left, dict) and isinstance(right, dict):
        return list(left) == list(right) and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            equivalent(a, b) for a, b in zip(left, right, strict=True)
        )
    return type(left) is type(right) and left == right

"""Mirrors clawrecipes/tests/stable-stringify.test.ts."""

from hermes_recipes.stable_stringify import stable_stringify


def test_sorts_object_keys_deterministically():
    a = {"z": 1, "a": 2, "m": 3}
    b = {"m": 3, "a": 2, "z": 1}
    assert stable_stringify(a) == stable_stringify(b)
    assert stable_stringify(a) == '{"a":2,"m":3,"z":1}'


def test_handles_arrays():
    assert stable_stringify([3, 1, 2]) == "[3,1,2]"
    assert stable_stringify([{"b": 1, "a": 2}]) == '[{"a":2,"b":1}]'


def test_handles_circular_references():
    c: dict = {"x": 1}
    c["self"] = c
    assert stable_stringify(c) == '{"self":"[Circular]","x":1}'


def test_handles_nested_objects():
    obj = {"outer": {"inner": {"z": 1, "a": 2}}}
    assert stable_stringify(obj) == '{"outer":{"inner":{"a":2,"z":1}}}'


def test_primitives_pass_through():
    assert stable_stringify(None) == "null"
    assert stable_stringify(42) == "42"
    assert stable_stringify("hi") == '"hi"'

"""Covers hermes_recipes/workflows/error_classify.py."""

from hermes_recipes.workflows.error_classify import (
    classify_error,
    error_category_label,
)


class _FakeToolError(Exception):
    def __init__(self, message: str, http_status: int = 0) -> None:
        super().__init__(message)
        self.http_status = http_status


def test_http_status_402_is_funding():
    assert classify_error(_FakeToolError("nope", http_status=402)) == "funding"


def test_http_status_429_is_rate_limit():
    assert classify_error(_FakeToolError("nope", http_status=429)) == "rate-limit"


def test_http_status_401_and_403_are_auth():
    assert classify_error(_FakeToolError("u", http_status=401)) == "auth"
    assert classify_error(_FakeToolError("u", http_status=403)) == "auth"


def test_http_status_408_and_504_are_timeout():
    assert classify_error(_FakeToolError("t", http_status=408)) == "timeout"
    assert classify_error(_FakeToolError("t", http_status=504)) == "timeout"


def test_message_patterns():
    assert classify_error(Exception("insufficient credits to continue")) == "funding"
    assert classify_error(Exception("Rate limit reached")) == "rate-limit"
    assert classify_error(Exception("unauthorized")) == "auth"
    assert classify_error(Exception("operation timed out")) == "timeout"


def test_timeout_exception_class():
    assert classify_error(TimeoutError("slow")) == "timeout"


def test_falls_back_to_unknown():
    assert classify_error(Exception("something else entirely")) == "unknown"


def test_label_for_each_category():
    for cat in ("funding", "rate-limit", "auth", "timeout", "unknown"):
        assert error_category_label(cat) != ""

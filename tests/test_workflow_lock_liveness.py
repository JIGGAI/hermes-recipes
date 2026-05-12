"""Covers hermes_recipes/workflows/lock_liveness.py."""

import os
import socket

from hermes_recipes.workflows.lock_liveness import (
    current_lock_owner,
    is_lock_holder_dead,
)


def test_current_lock_owner_reports_self():
    owner = current_lock_owner()
    assert owner.pid == os.getpid()
    assert owner.host == socket.gethostname()


def test_cross_host_lock_is_never_reclaimed():
    info = {"host": "some-other-host", "pid": 1}
    assert is_lock_holder_dead(info) is False


def test_missing_fields_treated_as_alive():
    assert is_lock_holder_dead({}) is False
    assert is_lock_holder_dead({"host": socket.gethostname()}) is False
    assert is_lock_holder_dead({"pid": -1, "host": socket.gethostname()}) is False


def test_same_host_alive_pid_is_alive():
    info = {"host": socket.gethostname(), "pid": os.getpid()}
    assert is_lock_holder_dead(info) is False


def test_same_host_dead_pid_is_dead():
    # PID 999_999_999 should not exist on any normal system.
    info = {"host": socket.gethostname(), "pid": 999_999_999}
    assert is_lock_holder_dead(info) is True

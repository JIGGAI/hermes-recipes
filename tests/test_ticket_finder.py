"""Mirrors clawrecipes/tests/ticket-finder.test.ts."""

from pathlib import Path

from hermes_recipes.ticket_finder import (
    all_lane_dirs,
    compute_next_ticket_number,
    find_ticket_file,
    lane_dir,
    parse_owner_from_md,
    parse_ticket_arg,
    parse_ticket_filename,
)


def test_lane_dir_returns_work_subdir():
    assert lane_dir("/team", "backlog") == Path("/team") / "work" / "backlog"
    assert lane_dir("/team", "in-progress") == Path("/team") / "work" / "in-progress"


def test_all_lane_dirs_returns_all_four():
    dirs = all_lane_dirs("/team")
    assert len(dirs) == 4
    expected = {"backlog", "in-progress", "testing", "done"}
    assert {d.name for d in dirs} == expected


def test_parse_ticket_arg_pads_numeric_shorthand():
    assert parse_ticket_arg("30") == {"ticket_arg": "0030", "ticket_num": "0030"}
    assert parse_ticket_arg("7") == {"ticket_arg": "0007", "ticket_num": "0007"}


def test_parse_ticket_arg_keeps_four_digit():
    assert parse_ticket_arg("0030") == {"ticket_arg": "0030", "ticket_num": "0030"}


def test_parse_ticket_arg_extracts_number_from_id():
    assert parse_ticket_arg("0007-some-ticket") == {
        "ticket_arg": "0007-some-ticket",
        "ticket_num": "0007",
    }


def test_parse_ticket_arg_returns_none_for_non_matching():
    r = parse_ticket_arg("abc")
    assert r["ticket_arg"] == "abc"
    assert r["ticket_num"] is None


def test_parse_ticket_filename_matches_and_misses():
    assert parse_ticket_filename("0042-foo-bar.md") == {
        "ticket_num_str": "0042",
        "slug": "foo-bar",
    }
    assert parse_ticket_filename("not-a-ticket.md") is None


def test_parse_owner_from_md():
    assert parse_owner_from_md("# Ticket\n\nOwner: alice\n\nBody") == "alice"
    assert parse_owner_from_md("Owner: bob") == "bob"
    assert parse_owner_from_md("# Ticket\n\nNo owner here") is None
    assert parse_owner_from_md("") is None


def test_find_ticket_file_by_number(tmp_path):
    backlog = tmp_path / "work" / "backlog"
    backlog.mkdir(parents=True)
    ticket = backlog / "0007-sample.md"
    ticket.write_text("# 0007-sample\n\nContent", encoding="utf-8")
    assert find_ticket_file(team_dir=tmp_path, ticket="7") == ticket


def test_find_ticket_file_returns_none_when_missing(tmp_path):
    (tmp_path / "work" / "backlog").mkdir(parents=True)
    assert find_ticket_file(team_dir=tmp_path, ticket="9999") is None


def test_compute_next_ticket_number_when_no_tickets(tmp_path):
    (tmp_path / "work" / "backlog").mkdir(parents=True)
    assert compute_next_ticket_number(tmp_path) == 1


def test_compute_next_ticket_number_returns_max_plus_one(tmp_path):
    backlog = tmp_path / "work" / "backlog"
    backlog.mkdir(parents=True)
    (backlog / "0003-old.md").write_text("# 0003", encoding="utf-8")
    in_progress = tmp_path / "work" / "in-progress"
    in_progress.mkdir(parents=True)
    (in_progress / "0015-current.md").write_text("# 0015", encoding="utf-8")
    assert compute_next_ticket_number(tmp_path) == 16

# -*- coding: utf-8 -*-
"""Date extraction.

This is the highest-stakes code in the repository. A date read the wrong way
round does not raise anything. It produces a chronology that is internally
consistent, properly cited, and wrong, and nobody downstream has any way to tell.
So the ambiguity handling is tested harder than anything else here.
"""
import pytest

from chronology import _yr, build, find_dates


class TestTwoDigitYears:
    """The 50 boundary is a convention, not a fact. Pin it so it cannot drift."""

    @pytest.mark.parametrize("raw,expected", [
        ("2024", 2024),     # already four digits, passed through
        ("1998", 1998),
        ("24", 2024),       # below 50 -> this century
        ("00", 2000),
        ("49", 2049),       # last year that reads as 20xx
        ("50", 1950),       # first year that reads as 19xx
        ("99", 1999),
    ])
    def test_expansion(self, raw, expected):
        assert _yr(raw) == expected


class TestUnambiguousFormats:
    def test_month_name_first(self):
        got = find_dates("Filed on March 4, 2026 in open court.", "unknown")
        assert [(d, amb) for d, amb, _, _, _ in got] == [("2026-03-04", False)]

    def test_day_first_written_out(self):
        got = find_dates("this 4th day of March, 2026", "unknown")
        assert [(d, amb) for d, amb, _, _, _ in got] == [("2026-03-04", False)]

    def test_iso(self):
        got = find_dates("Logged 2026-03-04 by the clerk.", "unknown")
        assert [(d, amb) for d, amb, _, _, _ in got] == [("2026-03-04", False)]

    def test_raw_text_and_offsets_are_returned(self):
        text = "Filed on March 4, 2026 in open court."
        (iso, _amb, raw, start, end), = find_dates(text, "unknown")
        assert raw == "March 4, 2026"
        assert text[start:end] == raw       # offsets must actually locate it


class TestNumericAmbiguity:
    """03/04/2026 is 4 March to half the world and 3 April to the other half."""

    def test_month_first_mode(self):
        (iso, amb, _, _, _), = find_dates("03/04/2026", "monthfirst")
        assert (iso, amb) == ("2026-03-04", False)

    def test_day_first_mode(self):
        (iso, amb, _, _, _), = find_dates("03/04/2026", "dayfirst")
        assert (iso, amb) == ("2026-04-03", False)

    def test_unknown_mode_flags_it_rather_than_guessing(self):
        (iso, amb, _, _, _), = find_dates("03/04/2026", "unknown")
        assert amb is True, "an unresolvable date must be flagged, never assumed"

    def test_first_part_over_twelve_can_only_be_a_day(self):
        # 25/03 cannot be month-first, so the mode is irrelevant and it is certain.
        for mode in ("unknown", "monthfirst", "dayfirst"):
            (iso, amb, _, _, _), = find_dates("25/03/2026", mode)
            assert (iso, amb) == ("2026-03-25", False), mode

    def test_second_part_over_twelve_can_only_be_a_month_first_date(self):
        for mode in ("unknown", "monthfirst", "dayfirst"):
            (iso, amb, _, _, _), = find_dates("03/25/2026", mode)
            assert (iso, amb) == ("2026-03-25", False), mode

    def test_impossible_date_is_dropped_not_coerced(self):
        # 45 is not a day in any reading. Silently clamping it would invent a fact.
        assert find_dates("13/45/2026", "unknown") == []

    def test_two_digit_year_in_numeric_form(self):
        (iso, _amb, _, _, _), = find_dates("03/25/26", "monthfirst")
        assert iso == "2026-03-25"


class TestBuild:
    def test_ambiguous_dates_stay_off_the_timeline(self, make_report, make_document,
                                                   make_page):
        rep = make_report([make_document(
            "motion.pdf", [make_page(1, "Served 03/04/2026 on the respondent.")])])
        entries, ambiguous = build(rep, "unknown")
        assert entries == [], "an ambiguous date must not be placed on the timeline"
        assert len(ambiguous) == 1

    def test_entries_carry_their_citation(self, make_report, make_document, make_page):
        rep = make_report([make_document(
            "motion.pdf", [make_page(7, "Filed on March 4, 2026.")])])
        entries, _ = build(rep, "unknown")
        assert entries[0]["doc"] == "motion.pdf"
        assert entries[0]["page"] == 7
        assert "March 4, 2026" in entries[0]["context"]

    def test_entries_are_sorted_chronologically(self, make_report, make_document,
                                                make_page):
        rep = make_report([make_document("a.pdf", [
            make_page(1, "Second event March 4, 2026. First event January 2, 2026."),
        ])])
        entries, _ = build(rep, "unknown")
        assert [e["date"] for e in entries] == ["2026-01-02", "2026-03-04"]

    def test_empty_pages_are_skipped_without_error(self, make_report, make_document,
                                                   make_page):
        rep = make_report([make_document("blank.pdf", [make_page(1, "   ")])])
        assert build(rep, "unknown") == ([], [])

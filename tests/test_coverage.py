# -*- coding: utf-8 -*-
"""The coverage gate.

This is the check that decides whether anyone is allowed to draw a conclusion
from the record. Its job is to fail loudly on a silent partial read, so the
tests are written from the other direction: each one constructs a specific way
a document set can be quietly incomplete and asserts the gate catches it.

A gate that cannot fail is not a gate, so there is also a test that a clean set
produces nothing - otherwise a always-failing gate would pass this file.
"""
from coverage import SCAN_TEXT_FLOOR, THIN_PAGE_FLOOR, check

GOOD = "This page carries a real paragraph of extracted text, comfortably past the floor."


def test_clean_set_raises_nothing(make_report, make_document, make_page):
    rep = make_report([make_document("a.pdf", [make_page(1, GOOD), make_page(2, GOOD)])])
    failures, warnings, docs = check(rep)
    assert failures == []
    assert warnings == []
    assert len(docs) == 1


def test_c1_a_file_that_was_never_ingested_fails(make_report):
    rep = make_report(skipped=[{"path": "exhibit_d.xlsx", "reason": "unsupported type .xlsx"}])
    failures, _warnings, _docs = check(rep)
    assert len(failures) == 1
    assert "NOT INGESTED" in failures[0] and "exhibit_d.xlsx" in failures[0]


def test_c2_page_count_mismatch_fails(make_report, make_document, make_page):
    """The container says 10 pages, extraction returned 3. Three pages of a ten
    page motion reads perfectly well and is missing the part that matters."""
    doc = make_document("motion.pdf", [make_page(i, GOOD) for i in (1, 2, 3)], declared=10)
    failures, _warnings, _docs = check(make_report([doc]))
    assert any("PAGE COUNT" in f for f in failures)
    assert any("declares 10" in f and "returned 3" in f for f in failures)


def test_c3_document_with_no_text_at_all_fails(make_report, make_document, make_page):
    doc = make_document("scan.pdf", [make_page(1, ""), make_page(2, "")])
    failures, _warnings, _docs = check(make_report([doc]))
    assert any("NO TEXT" in f for f in failures)


def test_c4_page_with_images_and_no_text_is_an_unread_scan(make_report, make_document,
                                                           make_page):
    """The dangerous one: a scanned page with no OCR. It has content, and nothing
    downstream will ever mention that nobody read it."""
    doc = make_document("exhibit.pdf", [make_page(1, GOOD),
                                        make_page(2, "Exhibit C", images=2)])
    failures, _warnings, _docs = check(make_report([doc]))
    unread = [f for f in failures if "UNREAD SCAN" in f]
    assert len(unread) == 1
    assert "p2" in unread[0] and "2 image(s)" in unread[0]


def test_c5_thin_page_without_images_is_a_warning_not_a_failure(make_report,
                                                                make_document, make_page):
    """A near-empty page with no images is usually a real divider page. Worth an
    eye, not worth blocking on - otherwise the gate cries wolf and gets ignored."""
    doc = make_document("a.pdf", [make_page(1, GOOD), make_page(2, "-- 4 --")])
    failures, warnings, _docs = check(make_report([doc]))
    assert failures == []
    assert any("THIN PAGE" in w for w in warnings)


def test_the_floors_are_where_the_behaviour_changes(make_report, make_document, make_page):
    """Pin the thresholds. Moving them silently changes what the gate lets past."""
    assert THIN_PAGE_FLOOR < SCAN_TEXT_FLOOR

    just_over = make_document("a.pdf", [make_page(1, "x" * THIN_PAGE_FLOOR)])
    failures, warnings, _ = check(make_report([just_over]))
    assert failures == [] and warnings == []

    just_under = make_document("b.pdf", [make_page(1, "x" * (THIN_PAGE_FLOOR - 1))])
    failures, warnings, _ = check(make_report([just_under]))
    assert failures == [] and len(warnings) == 1


def test_multiple_problems_are_all_reported(make_report, make_document, make_page):
    """One failure must not mask another, or fixing them becomes a queue."""
    rep = make_report(
        documents=[make_document("a.pdf", [make_page(1, "", images=1)], declared=5)],
        skipped=[{"path": "b.xlsx", "reason": "unsupported type .xlsx"}])
    failures, _warnings, _docs = check(rep)
    kinds = {f.split()[0] + " " + f.split()[1] for f in failures}
    assert {"NOT INGESTED", "PAGE COUNT", "NO TEXT", "UNREAD SCAN"} <= kinds

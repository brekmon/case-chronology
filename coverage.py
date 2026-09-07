#!/usr/bin/env python3
"""
coverage.py - prove the ingest actually read every page.

    python coverage.py ingest.json          exits non-zero if coverage fails

WHY THIS EXISTS
---------------
A document pipeline that misses pages does not crash. It returns a smaller
answer and reports success, and the smaller answer looks exactly like a complete
one. In discovery that is the worst failure available: you conclude a fact is
absent from the record when really the page it sits on was never read.

I learned this the expensive way on a different corpus. A scanner stopped eight
minutes into a five hour file and reported that it had finished. Nothing flagged
it. The output looked fine, because output always looks fine when the thing that
went wrong is an omission.

So this is a gate, not a report. It exits non-zero when coverage cannot be
proven, and it is meant to run before anybody draws a conclusion from the text.

THE DESIGN RULE, WHICH IS THE WHOLE POINT
------------------------------------------
A check only counts if a tool produced the number, or a human looked at the page.

Everything measurable is measured and the figure is printed. Everything this
script CANNOT determine is printed too, by name, as an outstanding manual check.
It is never silently omitted, because a gate that quietly skips a check teaches
you to trust it about things it never looked at.
"""
import argparse
import json
import sys

# A page with images and almost no text is a scan nobody read.
SCAN_TEXT_FLOOR = 40        # characters
# A text page this thin is usually a separator, but it is worth a human glance.
THIN_PAGE_FLOOR = 15        # characters


def check(report):
    docs = report.get("documents", [])
    skipped = report.get("skipped", [])
    failures, warnings = [], []

    # --- C1: every file in the folder was ingested ---------------------------
    for s in skipped:
        failures.append(f"NOT INGESTED  {s['path']}  ({s['reason']})")

    for d in docs:
        path = d["path"]

        # --- C2: pages read matches pages the container declares -------------
        if d["pages_read"] != d["pages_declared"]:
            failures.append(
                f"PAGE COUNT    {path}  container declares {d['pages_declared']}, "
                f"extraction returned {d['pages_read']}")

        # --- C3: a document that yielded no text at all ----------------------
        total = sum(p["chars"] for p in d["pages"])
        if total == 0:
            failures.append(f"NO TEXT       {path}  produced zero characters across "
                            f"{d['pages_read']} page(s)")

        for p in d["pages"]:
            # --- C4: images present, text absent. An unread scan -------------
            if p["chars"] < SCAN_TEXT_FLOOR and p["images"] > 0:
                failures.append(
                    f"UNREAD SCAN   {path} p{p['page']}  {p['images']} image(s), "
                    f"only {p['chars']} chars. This page has content nobody has read.")
            # --- C5: thin page, no images. Probably fine, worth an eye -------
            elif p["chars"] < THIN_PAGE_FLOOR:
                warnings.append(
                    f"THIN PAGE     {path} p{p['page']}  {p['chars']} chars, no images")

    return failures, warnings, docs


MANUAL_CHECKS = [
    "Handwriting, signatures and margin notes. Text extraction does not see ink.",
    "Redaction boxes. A black rectangle drawn over text may still leave the text "
    "extractable underneath, or may have removed content you needed.",
    "Tables and figures. The characters may extract while the STRUCTURE, and "
    "therefore the meaning of a row, does not.",
    "Attachments and exhibits referenced but not present in the folder.",
    "Whether this document set is complete. Nothing here can tell you about a "
    "document that was never produced.",
]


def main():
    ap = argparse.ArgumentParser(description="Prove an ingest covered every page.")
    ap.add_argument("report", nargs="?", default="ingest.json")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as failures too")
    a = ap.parse_args()

    try:
        with open(a.report, encoding="utf-8") as f:
            report = json.load(f)
    except FileNotFoundError:
        sys.exit(f"no such report: {a.report}. Run ingest.py first.")

    failures, warnings, docs = check(report)

    pages = sum(d["pages_read"] for d in docs)
    chars = sum(p["chars"] for d in docs for p in d["pages"])
    print(f"COVERAGE REPORT   {a.report}")
    print(f"  {len(docs)} document(s), {pages} page(s), {chars:,} characters\n")

    if failures:
        print(f"FAILED  {len(failures)} problem(s):\n")
        for f in failures:
            print("  " + f)
        print()
    else:
        print("PASSED  every declared page was read and produced text.\n")

    if warnings:
        print(f"{len(warnings)} warning(s):\n")
        for w in warnings:
            print("  " + w)
        print()

    # This block is not decoration. It is the half of the gate that keeps the
    # other half honest.
    print("CHECKS THIS TOOL CANNOT MAKE. A human has to do these:\n")
    for m in MANUAL_CHECKS:
        print(f"  [ ] {m}")
    print()

    bad = bool(failures) or (a.strict and bool(warnings))
    print("RESULT: " + ("COVERAGE NOT PROVEN, do not draw conclusions from this text"
                        if bad else "coverage proven for everything measurable"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

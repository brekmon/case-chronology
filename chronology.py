#!/usr/bin/env python3
"""
chronology.py - every date in the record, with the page it came from.

    python chronology.py ingest.json [-o chronology.md]

Sorting a matter by time is most of the analytical work, and doing it by hand is
where errors enter. This does the extraction; it does not do the thinking.

THE AMBIGUITY PROBLEM, WHICH IS THE POINT OF THIS TOOL
-------------------------------------------------------
"03/04/2024" is March 4th in the United States and April 3rd almost everywhere
else. Both readings are valid. Most date extractors pick one silently, and a
chronology built on a silent guess is worse than no chronology, because it looks
authoritative while being a month wrong.

So numeric dates where both parts could be a month are marked AMBIGUOUS and
reported separately. They are never quietly resolved. If the document set has a
convention you can establish, pass --dayfirst or --monthfirst and the assumption
becomes explicit and recorded in the output.

Every entry carries its document and page, because a date with no source cannot
be checked, and an unverifiable date is not evidence.
"""
import argparse
import json
import re
import sys
from collections import Counter

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})
MON = "|".join(sorted(MONTHS, key=len, reverse=True))

# "March 4, 2024" / "Mar. 4 2024"
RE_MDY = re.compile(rf"\b({MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
# "4 March 2024" / "6th day of May, 2024"
RE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({MON})\.?,?\s+(\d{{4}})\b", re.I)
# "2024-03-04"
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "03/04/2024" or "3/4/24"
RE_NUM = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")

CONTEXT = 90


def _yr(y):
    y = int(y)
    return y if y > 99 else (2000 + y if y < 50 else 1900 + y)


def find_dates(text, mode):
    """Yield (iso, ambiguous, raw, start, end)."""
    out = []
    for m in RE_MDY.finditer(text):
        mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), _yr(m.group(3))
        out.append((f"{y:04d}-{mo:02d}-{d:02d}", False, m.group(0), m.start(), m.end()))
    for m in RE_DMY.finditer(text):
        d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], _yr(m.group(3))
        out.append((f"{y:04d}-{mo:02d}-{d:02d}", False, m.group(0), m.start(), m.end()))
    for m in RE_ISO.finditer(text):
        out.append((f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                    False, m.group(0), m.start(), m.end()))
    for m in RE_NUM.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), _yr(m.group(3))
        # Both parts 12 or under: genuinely ambiguous unless told otherwise.
        ambiguous = a <= 12 and b <= 12 and mode == "unknown"
        mo, d = (b, a) if mode == "dayfirst" else (a, b)
        if a > 12:                      # can only be day-first
            mo, d, ambiguous = b, a, False
        elif b > 12:                    # can only be month-first
            mo, d, ambiguous = a, b, False
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        out.append((f"{y:04d}-{mo:02d}-{d:02d}", ambiguous, m.group(0), m.start(), m.end()))
    return out


def build(report, mode):
    entries, ambiguous = [], []
    for doc in report.get("documents", []):
        for page in doc["pages"]:
            text = page.get("text", "")
            if not text.strip():
                continue
            flat = re.sub(r"\s+", " ", text)
            for iso, amb, raw, s, e in find_dates(text, mode):
                # Re-locate in the whitespace-collapsed text for readable context
                idx = flat.find(raw)
                lo = max(0, idx - CONTEXT)
                ctx = flat[lo: idx + len(raw) + CONTEXT].strip()
                item = {"date": iso, "raw": raw, "doc": doc["path"],
                        "page": page["page"], "context": ctx, "ambiguous": amb}
                (ambiguous if amb else entries).append(item)
    entries.sort(key=lambda x: (x["date"], x["doc"], x["page"]))
    ambiguous.sort(key=lambda x: (x["doc"], x["page"]))
    return entries, ambiguous


def render(entries, ambiguous, mode, report):
    L = ["# Chronology", ""]
    L.append(f"Built from `{len(report.get('documents', []))}` document(s). "
             f"Every entry cites the document and page it came from.")
    L.append("")
    assumption = {"unknown": "none. Numeric dates that could be read either way are "
                             "listed separately as ambiguous and NOT placed on the timeline",
                  "monthfirst": "numeric dates read as MONTH/DAY/YEAR (US convention)",
                  "dayfirst": "numeric dates read as DAY/MONTH/YEAR"}[mode]
    L += [f"**Date-order assumption:** {assumption}.", ""]

    L += ["## Timeline", ""]
    if not entries:
        L.append("_No unambiguous dates found._")
    last = None
    for e in entries:
        if e["date"] != last:
            L.append(f"### {e['date']}")
            last = e["date"]
        L.append(f"- \"{e['context']}\"")
        L.append(f"  — `{e['doc']}` p{e['page']} (as written: \"{e['raw']}\")")
    L.append("")

    L += ["## Ambiguous dates, deliberately NOT placed on the timeline", ""]
    if not ambiguous:
        L.append("_None._")
    else:
        L.append("Each of these is numeric with both parts 12 or under, so it could be "
                 "read two ways. Resolve them against the document set, then re-run "
                 "with `--monthfirst` or `--dayfirst`.")
        L.append("")
        for e in ambiguous:
            a, b, y = re.split(r"[/.]", e["raw"])
            L.append(f"- **{e['raw']}** could be {int(a):02d} {int(b):02d} or "
                     f"{int(b):02d} {int(a):02d} of {_yr(y)}")
            L.append(f"  — `{e['doc']}` p{e['page']}: \"{e['context']}\"")
    L.append("")

    L += ["## What this cannot tell you", "",
          "- A date written in words with no numerals (\"the following spring\")",
          "- Whether a date in a document is the date the event happened, the date "
          "it was recorded, or a date being alleged by one side",
          "- Anything about a document that was never produced",
          "- Whether two documents describing the same day agree", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Build a cited chronology from an ingest.")
    ap.add_argument("report", nargs="?", default="ingest.json")
    ap.add_argument("-o", "--out", default="chronology.md")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--monthfirst", action="store_true", help="read 03/04 as March 4")
    g.add_argument("--dayfirst", action="store_true", help="read 03/04 as 3 April")
    a = ap.parse_args()

    mode = "monthfirst" if a.monthfirst else "dayfirst" if a.dayfirst else "unknown"

    try:
        with open(a.report, encoding="utf-8") as f:
            report = json.load(f)
    except FileNotFoundError:
        sys.exit(f"no such report: {a.report}. Run ingest.py first.")

    entries, ambiguous = build(report, mode)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(entries, ambiguous, mode, report))

    span = f"{entries[0]['date']} to {entries[-1]['date']}" if entries else "n/a"
    print(f"  {len(entries)} dated reference(s), spanning {span}")
    print(f"  {len(ambiguous)} ambiguous date(s) held back from the timeline")
    if ambiguous and mode == "unknown":
        print("  Resolve those, then re-run with --monthfirst or --dayfirst.")
    docs = Counter(e["doc"] for e in entries)
    for d, n in docs.most_common():
        print(f"      {n:3d}  {d}")
    print(f"  wrote {a.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
claims.py - test an assertion against the record.

    python claims.py ingest.json claims.txt [-o claims.md]

For each claim you give it, this returns the passages that support it, the
passages that appear to contradict it, and one of three verdicts:

    SUPPORTED       passages back this up
    CONTRADICTED    passages appear to say otherwise
    UNSUPPORTED     nothing in the record speaks to this at all

THE THIRD VERDICT IS THE ENTIRE REASON THIS EXISTS
---------------------------------------------------
Most retrieval tools return nothing when they find nothing, and a reader
interprets an empty result as "there is nothing there". Those are different
statements. "The record does not address this" and "I could not find it" and
"you asked badly" all look identical when a tool returns an empty list.

So UNSUPPORTED is stated out loud, as a verdict, every time. It is the most
common honest answer about any claim in a document set and the one that most
often changes what somebody does next.

WHY THE MATCHING IS DELIBERATELY DUMB
--------------------------------------
This uses term overlap and proximity, not embeddings. That is a choice, not a
limitation of effort.

In a legal setting you have to be able to say WHY a passage was returned. A
transparent matcher that misses things you can then search for by hand beats a
black box that returns a confident, unexplainable ranking. Every hit below
prints the terms that caused it, so you can judge the match yourself rather than
trusting a score you cannot inspect.

NOT LEGAL ANALYSIS
------------------
This is a retrieval aid. It finds text near your words. It does not read, weigh
evidence, understand context or know what any of it means. A CONTRADICTED
verdict means a negation appeared near your terms, which is a hint to go and
look, not a finding.
"""
import argparse
import json
import re
import sys

STOP = set("""a an and are as at be been being but by for from had has have if in into is it
its of on or that the their there this to was were what when which who will with your you
i he she they them his her not no nor""".split())

NEGATIONS = {"no", "not", "never", "none", "nothing", "neither", "nor", "without",
             "denied", "denies", "deny", "failed", "fails", "refused", "refuses",
             "did not", "was not", "were not", "has not", "have not", "cannot",
             "unable", "absent", "omitted", "never received", "no responses"}

MIN_TERMS = 2          # a single shared word is a coincidence, not a match
CONTEXT = 110


def terms(s):
    return [w for w in re.findall(r"[a-z0-9$][a-z0-9$'.,-]*", s.lower())
            if w not in STOP and len(w) > 2]


def passages(report):
    """Every sentence in the record, carrying its citation."""
    out = []
    for doc in report.get("documents", []):
        for page in doc["pages"]:
            text = page.get("text", "")
            if not text.strip():
                continue
            flat = re.sub(r"\s+", " ", text).strip()
            for sent in re.split(r"(?<=[.;:])\s+(?=[A-Z0-9])", flat):
                if len(sent) > 12:
                    out.append({"text": sent, "doc": doc["path"], "page": page["page"]})
    return out


# Longest first, then alphabetically. Two reasons, and the first one is a bug fix:
# iterating NEGATIONS directly walks a SET, whose order changes between processes
# because Python randomises string hashing. "did not produce" contains both "not"
# and "did not", so the same sentence could report either one depending on the
# run. A tool that exists to make text verifiable cannot give different answers
# to the same question. Sorting also means the most specific phrase wins, so a
# reader sees "did not" rather than the less informative "not".
NEGATIONS_BY_SPECIFICITY = sorted(NEGATIONS, key=lambda n: (-len(n), n))


def has_negation(sentence):
    low = " " + sentence.lower() + " "
    for n in NEGATIONS_BY_SPECIFICITY:
        if f" {n} " in low:
            return n
    return None


def assess(claim, pool):
    want = set(terms(claim))
    if not want:
        return "UNSUPPORTED", [], [], want
    support, contra = [], []
    for p in pool:
        got = set(terms(p["text"]))
        shared = want & got
        if len(shared) < MIN_TERMS:
            continue
        hit = dict(p)
        hit["matched"] = sorted(shared)
        hit["score"] = len(shared) / len(want)
        neg = has_negation(p["text"])
        if neg:
            hit["negation"] = neg
            contra.append(hit)
        else:
            support.append(hit)
    support.sort(key=lambda h: -h["score"])
    contra.sort(key=lambda h: -h["score"])
    if not support and not contra:
        verdict = "UNSUPPORTED"
    elif contra and not support:
        verdict = "CONTRADICTED"
    elif contra and support:
        verdict = "DISPUTED"
    else:
        verdict = "SUPPORTED"
    return verdict, support[:5], contra[:5], want


def render(results):
    L = ["# Claim verification", "",
         "Each claim was tested against every sentence in the record. "
         "Matching is term overlap, shown per hit so you can judge it yourself.",
         "",
         "| Verdict | Meaning |",
         "|---|---|",
         "| SUPPORTED | passages back this up |",
         "| CONTRADICTED | passages near your terms carry a negation |",
         "| DISPUTED | both support and contradiction found |",
         "| **UNSUPPORTED** | **nothing in the record speaks to this at all** |",
         ""]
    for r in results:
        L += [f"## {r['verdict']}  —  {r['claim']}", ""]
        if r["verdict"] == "UNSUPPORTED":
            L += ["Nothing in the ingested record matched two or more of the "
                  f"significant terms in this claim (`{', '.join(sorted(r['terms']))}`).",
                  "",
                  "That is not the same as the claim being false. It means the record "
                  "as ingested does not address it. Before concluding anything, check "
                  "that coverage.py passed, and that the document you expect this to "
                  "come from is actually in the folder.", ""]
            continue
        for label, hits in (("Supporting", r["support"]), ("Contradicting", r["contra"])):
            if not hits:
                continue
            L += [f"**{label}:**", ""]
            for h in hits:
                snip = h["text"][:2 * CONTEXT] + ("..." if len(h["text"]) > 2 * CONTEXT else "")
                L.append(f"- \"{snip}\"")
                extra = f", negation: \"{h['negation']}\"" if "negation" in h else ""
                L.append(f"  — `{h['doc']}` p{h['page']} "
                         f"(matched: {', '.join(h['matched'])}{extra})")
            L.append("")
    L += ["---", "",
          "**This is a retrieval aid, not legal analysis.** It finds text near your "
          "words. A CONTRADICTED verdict means a negation appeared near your terms, "
          "which is a reason to go and read the page, not a finding.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Test claims against an ingested record.")
    ap.add_argument("report", nargs="?", default="ingest.json")
    ap.add_argument("claims", nargs="?", default="claims.txt",
                    help="one claim per line; # comments ignored")
    ap.add_argument("-o", "--out", default="claims.md")
    a = ap.parse_args()

    try:
        with open(a.report, encoding="utf-8") as f:
            report = json.load(f)
    except FileNotFoundError:
        sys.exit(f"no such report: {a.report}. Run ingest.py first.")
    try:
        with open(a.claims, encoding="utf-8") as f:
            claim_list = [ln.strip() for ln in f
                          if ln.strip() and not ln.lstrip().startswith("#")]
    except FileNotFoundError:
        sys.exit(f"no such claims file: {a.claims}")

    # Corpus contamination guard. If the claims file itself got ingested, every
    # claim matches a copy of itself and every verdict is meaningless. This
    # happened during development: the example claims lived inside the samples
    # folder, ingest read it as evidence, and five claims came back SUPPORTED by
    # a document that was just the questions written down.
    import os
    claims_name = os.path.basename(a.claims).lower()
    ingested = [d["path"] for d in report.get("documents", [])]
    contaminated = [p for p in ingested if os.path.basename(p).lower() == claims_name]
    if contaminated:
        sys.exit(f"REFUSING TO RUN: the claims file appears in the ingested record "
                 f"as {contaminated[0]}. Every claim would match itself. Move the "
                 f"claims file outside the folder you ingest, then re-run ingest.py.")

    pool = passages(report)
    print(f"  {len(pool)} passage(s) in the record")

    results = []
    for c in claim_list:
        v, sup, con, want = assess(c, pool)
        results.append({"claim": c, "verdict": v, "support": sup,
                        "contra": con, "terms": want})
        print(f"  {v:<13} {c[:66]}")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(results))

    unsup = sum(1 for r in results if r["verdict"] == "UNSUPPORTED")
    print(f"\n  {len(results)} claim(s), {unsup} unsupported by the record as ingested")
    print(f"  wrote {a.out}")


if __name__ == "__main__":
    main()

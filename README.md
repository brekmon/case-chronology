# case-chronology

[![CI](https://github.com/brekmon/case-chronology/actions/workflows/ci.yml/badge.svg)](https://github.com/brekmon/case-chronology/actions/workflows/ci.yml)

Tooling for reading a folder of legal documents and refusing to assert anything
the documents do not support.

---

## The rule this is built on

> A claim only counts if a document supports it, and the citation is part of the
> claim.

Text with no source is not evidence. It is a rumour with good formatting.

Everything here follows from that: extraction keeps the page it came from,
conclusions carry citations, and the pipeline proves it read the whole record
before anyone is allowed to draw an inference from it.

---

## The problem this is actually solving

A document pipeline that misses pages does not crash. It returns a smaller
answer and reports success. **The smaller answer looks exactly like a complete
one.**

In discovery that is the worst failure available. You conclude a fact is absent
from the record, when really the page it sits on was scanned sideways, or the
extractor stopped early, or the exhibit was never produced at all. Nothing tells
you. The output looks fine, because output always looks fine when the thing that
went wrong is an omission.

So the first tool built here is not the clever one. It is the one that proves
the reading happened.

---

## What is here now

### `ingest.py` — page-anchored extraction

```bash
python ingest.py <folder> -o ingest.json
```

Walks a folder, extracts text from PDF, DOCX and TXT, and records per page: the
character count, the word count, **the number of images**, and whether a text
layer existed at all. Each document also carries a SHA-256, so if a file changes
between runs every citation drawn from it is known to be suspect.

Those image counts exist for one reason. A scanned page returns an empty string,
and an empty string looks identical to a genuinely blank page. Counting images
is what separates *there was nothing here* from **there was something here and I
could not read it**.

### `coverage.py` — the gate

```bash
python coverage.py ingest.json      # exits non-zero when coverage is not proven
```

| Check | What it catches |
|---|---|
| Not ingested | A file in the folder that no reader could open |
| Page count | Extraction returned fewer pages than the container declares |
| No text | A document that produced zero characters |
| Unread scan | A page with images and almost no text. Content nobody has read |
| Thin page | Very short pages, flagged for a human glance |

Run against the sample set, it finds the planted defect:

```
FAILED  2 problem(s):

  NO TEXT       04_exhibit_c_scanned.pdf  produced zero characters across 1 page(s)
  UNREAD SCAN   04_exhibit_c_scanned.pdf p1  1 image(s), only 0 chars.
                This page has content nobody has read.

RESULT: COVERAGE NOT PROVEN, do not draw conclusions from this text
```

**It also prints, every time, the checks it cannot make.** Handwriting.
Redaction boxes that may or may not have removed the text underneath. Table
structure, which can be lost while the characters survive. Exhibits referenced
but absent. Whether the production is complete at all.

Those are never silently omitted, because a gate that quietly skips a check
teaches you to trust it about things it never looked at. Naming them is the half
of the tool that keeps the other half honest.

### `chronology.py` — every date, with its citation

```bash
python chronology.py ingest.json -o chronology.md
```

Extracts every date in the record, sorted, each carrying the document and page
it came from.

**The point of it is the dates it refuses to place.** `03/04/2024` is March 4th
in the United States and April 3rd almost everywhere else. Both readings are
valid. Most extractors pick one silently, and a chronology built on a silent
guess is worse than none, because it looks authoritative while being a month
wrong. Ambiguous numeric dates are listed separately and kept off the timeline
until you resolve them and re-run with `--monthfirst` or `--dayfirst`. The
assumption you chose is printed at the top of the output.

### `claims.py` — assert something, see if the record backs it

```bash
python claims.py ingest.json claims.txt -o claims.md
```

| Verdict | Meaning |
|---|---|
| SUPPORTED | passages back this up |
| CONTRADICTED | passages near your terms carry a negation |
| DISPUTED | both were found |
| **UNSUPPORTED** | **nothing in the record speaks to this at all** |

**The fourth verdict is the whole reason this exists.** Most retrieval tools
return nothing when they find nothing, and a reader reads an empty result as
"there is nothing there". But "the record does not address this", "I could not
find it" and "you asked badly" all look identical when a tool returns an empty
list. So UNSUPPORTED is stated out loud, every time.

The matching is deliberately transparent: term overlap, with the matched terms
printed on every hit. In a legal setting you have to be able to say *why* a
passage came back. A simple matcher you can audit beats a black box that returns
a confident ranking you cannot inspect.

It also **refuses to run if your claims file was itself ingested as evidence.**
That guard exists because it happened during development: the example claims sat
inside the samples folder, ingest read them as a document, and every claim came
back SUPPORTED by a file that was just the questions written down.


---

## Quick start

```bash
pip install -r requirements.txt
python samples/make_samples.py                        # synthetic document set
python ingest.py samples -o ingest.json
python coverage.py ingest.json                        # will fail, on purpose
python chronology.py ingest.json -o chronology.md
python claims.py ingest.json claims.example.txt -o claims.md
```

Keep your claims file OUTSIDE the folder you ingest. `claims.py` will stop you
if you forget, but the tidier habit is to never put working files in with
evidence.

---

## About the sample documents

**Every sample is invented and generated by a script rather than committed.**
The parties, dates, figures and the matter itself do not exist. Generating them
means you can verify that yourself in thirty seconds rather than taking a
README's word for it.

The sample matter is a commercial contract dispute. The tooling is
domain-general and a neutral matter type keeps the demonstration about the
software.

One exhibit is deliberately generated as an image with no text layer, exactly
like a page that was scanned and never OCR'd. `coverage.py` is supposed to catch
it. **If you change the samples, keep something broken in them.** A gate you have
never seen fail is a gate you have no reason to trust.

If you want to try this on real material, use published opinions or other
genuine public record. Never use a live matter, and never use redacted
documents: redaction failures are common and a repository is permanent.

---

## Honest limitations

- **No OCR.** Scanned pages are detected and reported, not read. Wiring in
  Tesseract would close that, and reading a page badly is worse than knowing you
  have not read it, so the current behaviour is to fail loudly.
- **DOCX has no pages.** Word documents have no pagination until rendered, so
  they are recorded as a single unit and labelled as such rather than being
  given a fictional page number that someone might cite.
- **Table structure is not preserved.** Characters extract; the meaning of a row
  often does not. This is on the manual checklist for that reason.
- **Nothing here knows what was never produced.** No tool can.

---

## Tests

```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

75 tests. They run on every push against Python 3.10 through 3.13, and the
weight is deliberately uneven, because the failures worth catching here are not
crashes.

- **Date ambiguity** is tested hardest. `03/04/2026` is 4 March to half the
  world and 3 April to the other half, and reading it the wrong way round raises
  nothing at all: it produces a chronology that is internally consistent,
  properly cited, and wrong. The tests pin every branch, including that an
  unresolvable date is held off the timeline instead of guessed at, and that an
  impossible date is dropped rather than quietly clamped into a real one.
- **Negation handling**, because term overlap alone would report "the respondent
  did not produce the statements" as *support* for the claim that they did.
- **The coverage gate**, from the other direction: each test builds a specific
  way a document set can be silently incomplete — a page count that does not
  match the container, a scanned page with no text layer, a file that was never
  ingested — and asserts the gate catches it. One test asserts a clean set
  produces nothing, so a gate that always failed could not pass the suite.
- **What git is allowed to track.** This is a legal-document tool published in
  the open, so "no case material is committed" cannot be left to habit. CI fails
  the build if `ingest.json`, `chronology.md`, `claims.md`, `.private-terms` or
  any sample document is ever tracked.

CI also runs the whole pipeline end to end on the generated corpus. That job
requires the coverage gate to **fail**, because sample 04 is a scanned page
included on purpose. A gate that passed there would mean the check had stopped
working.

---

## Planned

- `disclosure_diff.py` — compare two versions of a financial statement and
  surface every line that appeared, vanished or changed
- `redact.py` — strip names, addresses and account numbers before sharing
- OCR, so scanned pages can be read rather than only detected

## Licence

MIT. See `LICENSE`.

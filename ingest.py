#!/usr/bin/env python3
"""
ingest.py - turn a folder of case documents into page-anchored text.

    python ingest.py <folder> [-o ingest.json]

Every extracted passage keeps the document and page it came from, because a
citation is part of a claim. Text with no source is not evidence, it is a
rumour with good formatting.

WHAT IT RECORDS, AND WHY EACH FIELD EARNS ITS PLACE
---------------------------------------------------
    sha256          provenance. If a document changes between runs, every
                    citation drawn from it is suspect and you need to know.
    pages_declared  what the container SAYS it holds
    pages_read      what extraction actually returned
    chars, words    per page, so a page that yielded nothing is visible
    images          per page, so a page with pictures and no text can be
                    identified as a scan that was never read
    text_layer      whether this page had extractable text at all

Those last two exist for one reason: a scanned page returns an empty string,
and an empty string looks exactly like a blank page. Without counting images
you cannot tell "there was nothing here" from "there was something here and I
could not read it". That distinction is the whole ballgame in discovery.

This script does not judge coverage. It records what happened and hands the
judgement to coverage.py, which is a separate step on purpose: measurement and
verdict should not live in the same function.

Requires: pymupdf. python-docx for .docx. Both optional at import time so the
tool degrades loudly rather than failing to start.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

SUPPORTED = (".pdf", ".docx", ".txt")

# Files that plainly are not evidence. Ignored without comment, because a gate
# that cries about its own tooling trains you to skim its output.
IGNORE = {".py", ".json", ".md", ".yml", ".yaml", ".ini", ".gitignore", ".log"}

# Files that COULD hold evidence but cannot be read here. These are reported, not
# ignored: a scanned exhibit sitting unreadable in the folder is exactly the kind
# of omission this whole tool exists to surface.
POSSIBLE_EVIDENCE = {".doc", ".rtf", ".odt", ".pages", ".tif", ".tiff",
                     ".jpg", ".jpeg", ".png", ".heic", ".eml", ".msg", ".xls", ".xlsx"}


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def read_pdf(path):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            raise RuntimeError("pymupdf is required to read PDFs: pip install pymupdf")

    doc = pymupdf.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        pages.append({
            "page": i,
            "text": text,
            "chars": len(text.strip()),
            "words": len(text.split()),
            "images": len(page.get_images(full=True)),
            "text_layer": bool(text.strip()),
        })
    declared = doc.page_count
    doc.close()
    return declared, pages


def read_docx(path):
    try:
        import docx
    except ImportError:
        raise RuntimeError("python-docx is required to read .docx: pip install python-docx")
    d = docx.Document(path)
    # A .docx has no page concept until it is rendered, so the whole document is
    # recorded as one unit. Saying "page 1 of 1" here would be a lie a reader
    # could cite, so the field is named honestly instead.
    text = "\n".join(p.text for p in d.paragraphs)
    return 1, [{
        "page": 1, "text": text, "chars": len(text.strip()),
        "words": len(text.split()), "images": 0,
        "text_layer": bool(text.strip()), "pagination": "not paginated (docx)",
    }]


def read_txt(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return 1, [{
        "page": 1, "text": text, "chars": len(text.strip()),
        "words": len(text.split()), "images": 0, "text_layer": bool(text.strip()),
    }]


READERS = {".pdf": read_pdf, ".docx": read_docx, ".txt": read_txt}


def ingest(root):
    docs, skipped = [], []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(dirpath, fn)
            if ext in IGNORE or fn.startswith("."):
                continue
            if ext not in SUPPORTED:
                reason = ("readable format but no reader installed" if ext in POSSIBLE_EVIDENCE
                          else f"unsupported type {ext}")
                skipped.append({"path": os.path.relpath(full, root).replace("\\", "/"),
                                "reason": reason})
                continue
            rel = os.path.relpath(full, root)
            try:
                declared, pages = READERS[ext](full)
                docs.append({
                    "path": rel.replace("\\", "/"),
                    "type": ext.lstrip("."),
                    "bytes": os.path.getsize(full),
                    "sha256": sha256(full),
                    "pages_declared": declared,
                    "pages_read": len(pages),
                    "pages": pages,
                })
                print(f"  read  {rel}  ({len(pages)} page(s))")
            except Exception as e:
                # A document that failed to open is NOT silently dropped. It is
                # recorded, so coverage.py can fail on it.
                skipped.append({"path": rel.replace("\\", "/"), "reason": f"{type(e).__name__}: {e}"})
                print(f"  FAIL  {rel}  {type(e).__name__}: {e}", file=sys.stderr)
    return docs, skipped


def main():
    ap = argparse.ArgumentParser(description="Page-anchored ingest of a document set.")
    ap.add_argument("folder")
    ap.add_argument("-o", "--out", default="ingest.json")
    a = ap.parse_args()

    if not os.path.isdir(a.folder):
        sys.exit(f"not a folder: {a.folder}")

    print(f"ingesting {a.folder}")
    docs, skipped = ingest(a.folder)

    out = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "root": os.path.abspath(a.folder),
        "documents": docs,
        "skipped": skipped,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    tp = sum(d["pages_read"] for d in docs)
    tc = sum(p["chars"] for d in docs for p in d["pages"])
    print(f"\n  {len(docs)} document(s), {tp} page(s), {tc:,} characters")
    if skipped:
        print(f"  {len(skipped)} file(s) not ingested. coverage.py will fail on these.")
    print(f"  wrote {a.out}")
    print("\n  Next: python coverage.py " + a.out)


if __name__ == "__main__":
    main()

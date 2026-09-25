# -*- coding: utf-8 -*-
"""Shared fixtures.

The tools are single-file modules at the repository root, so the root goes on
sys.path rather than turning the project into a package purely to satisfy the
test runner. Layout should serve the tool, not the other way round.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def page(number=1, text="", chars=None, images=0):
    """One page as ingest.py records it."""
    return {
        "page": number,
        "text": text,
        "chars": len(text.strip()) if chars is None else chars,
        "words": len(text.split()),
        "images": images,
        "text_layer": bool(text.strip()),
    }


def document(path="doc.pdf", pages=None, declared=None):
    pages = pages or [page()]
    return {
        "path": path,
        "pages": pages,
        "pages_read": len(pages),
        "pages_declared": len(pages) if declared is None else declared,
    }


def report(documents=None, skipped=None):
    return {"documents": documents or [], "skipped": skipped or []}


@pytest.fixture
def make_report():
    return report


@pytest.fixture
def make_document():
    return document


@pytest.fixture
def make_page():
    return page

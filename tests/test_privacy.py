# -*- coding: utf-8 -*-
"""The privacy gate, and what git is allowed to track.

This repository's whole argument is that a document pipeline must prove what it
did rather than claim it. The same standard applies to the repository itself: it
is a legal-document tool published in the open, so "no case material is
committed" cannot be a habit. It has to be enforced, and enforcement that only
runs on the author's laptop is not enforcement.

These tests run in CI on every push. If a real matter's output is ever staged,
the build fails before the push is merged, not after someone notices.
"""
import os
import subprocess

import pytest

import privacy_check

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=REPO)
    return [f for f in out.stdout.split() if f]


class TestNothingSensitiveIsTracked:
    """Each of these is a file that, on a live matter, holds privileged content."""

    @pytest.mark.parametrize("name", [
        ".private-terms",     # the screening word list is itself the leak
        "ingest.json",        # extracted text of every page
        "chronology.md",      # dated events with quoted context
        "claims.md",          # the claims and their supporting passages
        "coverage.txt",
        "claims.txt",         # the real claims file; only the .example ships
    ])
    def test_artifact_is_not_committed(self, name):
        assert name not in tracked(), (
            "%s is tracked by git. On a real matter this file carries privileged "
            "text straight into a public commit." % name)

    def test_no_sample_documents_are_committed(self):
        """Only the generator ships, so anyone can confirm the corpus is synthetic
        rather than take it on trust."""
        bad = [f for f in tracked()
               if f.startswith("samples/") and not f.endswith(".py")]
        assert bad == [], "sample documents must be generated, not committed: %s" % bad

    def test_the_example_terms_file_does_ship(self):
        """The gate is useless if nobody knows to set it up."""
        assert ".private-terms.example" in tracked()


class TestLoadTerms:
    def test_missing_file_stops_rather_than_passing(self, tmp_path, monkeypatch):
        """An absent word list must never be treated as 'nothing to screen for'."""
        monkeypatch.setattr(privacy_check, "TERMS_FILE", str(tmp_path / "nope"))
        with pytest.raises(SystemExit):
            privacy_check.load_terms()

    def test_empty_file_stops_rather_than_passing(self, tmp_path, monkeypatch):
        """An empty gate always passes, which is the same as having no gate."""
        f = tmp_path / "terms"
        f.write_text("# only a comment\n\n", encoding="utf-8")
        monkeypatch.setattr(privacy_check, "TERMS_FILE", str(f))
        with pytest.raises(SystemExit):
            privacy_check.load_terms()

    def test_terms_are_loaded_and_counted(self, tmp_path, monkeypatch):
        f = tmp_path / "terms"
        f.write_text("# a comment\nAcme Holdings\n2026DR30027\n\n", encoding="utf-8")
        monkeypatch.setattr(privacy_check, "TERMS_FILE", str(f))
        pattern, n = privacy_check.load_terms()
        assert n == 2
        assert pattern.search("filed by ACME HOLDINGS today"), "must be case-insensitive"
        assert pattern.search("case 2026DR30027")
        assert not pattern.search("nothing sensitive here")

    def test_regex_characters_in_a_term_are_escaped(self, tmp_path, monkeypatch):
        """A term like 'A. Person' must match literally, not as a wildcard."""
        f = tmp_path / "terms"
        f.write_text("A. Person\n", encoding="utf-8")
        monkeypatch.setattr(privacy_check, "TERMS_FILE", str(f))
        pattern, _n = privacy_check.load_terms()
        assert pattern.search("A. Person")
        assert not pattern.search("AXPerson"), "the dot must be literal, not a wildcard"

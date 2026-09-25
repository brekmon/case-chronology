# -*- coding: utf-8 -*-
"""Ingest: hashing, text reading, and the walk.

No PDF library is needed here. read_pdf imports pymupdf lazily inside the
function, so these tests exercise the walker and the plain-text path on any
machine, which keeps CI honest even if a binary wheel is unavailable.
"""
import hashlib
import os

from ingest import POSSIBLE_EVIDENCE, READERS, ingest, read_txt, sha256


class TestSha256:
    def test_matches_the_standard_library(self, tmp_path):
        p = tmp_path / "a.txt"
        data = b"the respondent produced the statements\n"
        p.write_bytes(data)
        assert sha256(str(p)) == hashlib.sha256(data).hexdigest()

    def test_chunking_does_not_change_the_digest(self, tmp_path):
        """The reader streams in 1 MiB blocks. A file larger than one block must
        hash identically to one read whole, or the manifest is meaningless."""
        p = tmp_path / "big.bin"
        data = os.urandom(3 * 1024 * 1024 + 17)
        p.write_bytes(data)
        assert sha256(str(p)) == hashlib.sha256(data).hexdigest()
        assert sha256(str(p), chunk=64) == hashlib.sha256(data).hexdigest()

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        assert sha256(str(p)) == hashlib.sha256(b"").hexdigest()


class TestReadTxt:
    def test_returns_one_page_with_counts(self, tmp_path):
        p = tmp_path / "note.txt"
        p.write_text("Two words here.", encoding="utf-8")
        declared, pages = read_txt(str(p))
        assert declared == 1 and len(pages) == 1
        assert pages[0]["page"] == 1
        assert pages[0]["words"] == 3
        assert pages[0]["text_layer"] is True

    def test_undecodable_bytes_do_not_raise(self, tmp_path):
        """A corrupt byte in one file must not abort the ingest of a whole set."""
        p = tmp_path / "bad.txt"
        p.write_bytes(b"valid text \xff\xfe more text")
        _declared, pages = read_txt(str(p))
        assert "valid text" in pages[0]["text"]

    def test_whitespace_only_has_no_text_layer(self, tmp_path):
        p = tmp_path / "blank.txt"
        p.write_text("   \n\t\n", encoding="utf-8")
        _declared, pages = read_txt(str(p))
        assert pages[0]["chars"] == 0
        assert pages[0]["text_layer"] is False


class TestWalk:
    def test_reads_supported_and_records_the_rest(self, tmp_path):
        (tmp_path / "a.txt").write_text("Some real content here.", encoding="utf-8")
        (tmp_path / "b.xlsx").write_bytes(b"not really a spreadsheet")
        (tmp_path / "c.zzz").write_bytes(b"nonsense")
        docs, skipped = ingest(str(tmp_path))

        assert [d["path"] for d in docs] == ["a.txt"]
        assert docs[0]["sha256"] and docs[0]["bytes"] > 0

        by_path = {s["path"]: s["reason"] for s in skipped}
        assert set(by_path) == {"b.xlsx", "c.zzz"}
        # An .xlsx is plausibly evidence, so it is reported differently from junk.
        assert "xlsx" in POSSIBLE_EVIDENCE or ".xlsx" in POSSIBLE_EVIDENCE
        assert by_path["b.xlsx"] != by_path["c.zzz"]

    def test_nothing_is_dropped_silently(self, tmp_path):
        """Every non-hidden file must come back as either read or skipped. This is
        the whole premise of the coverage gate downstream."""
        names = ["one.txt", "two.xlsx", "three.zzz", "four.txt"]
        for n in names:
            (tmp_path / n).write_text("content", encoding="utf-8")
        docs, skipped = ingest(str(tmp_path))
        assert len(docs) + len(skipped) == len(names)

    def test_nested_folders_are_walked_with_relative_paths(self, tmp_path):
        sub = tmp_path / "exhibits" / "2026"
        sub.mkdir(parents=True)
        (sub / "deep.txt").write_text("nested content", encoding="utf-8")
        docs, _skipped = ingest(str(tmp_path))
        assert docs[0]["path"] == "exhibits/2026/deep.txt", "paths must be posix-style"

    def test_dotfiles_are_ignored(self, tmp_path):
        (tmp_path / ".private-terms").write_text("secret", encoding="utf-8")
        (tmp_path / "real.txt").write_text("content", encoding="utf-8")
        docs, skipped = ingest(str(tmp_path))
        assert [d["path"] for d in docs] == ["real.txt"]
        assert skipped == []


def test_reader_table_covers_the_supported_extensions():
    assert set(READERS) == {".pdf", ".docx", ".txt"}

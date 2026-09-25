# -*- coding: utf-8 -*-
"""Claim assessment.

The failure that matters here is not a missed match. It is a claim reported as
SUPPORTED by a sentence that actually denies it, because the tool matched words
and words are all it sees. Negation handling is therefore the core of this file.

Note the deliberately modest contract: these verdicts mean "text near your terms
was found", not "this is true". The tests assert the tool's actual behaviour,
including where it is blunt, rather than pretending it reasons.
"""
import os

import pytest

from claims import MIN_TERMS, assess, has_negation, passages, terms


def passage(text, doc="record.pdf", page=1):
    return {"text": text, "doc": doc, "page": page}


class TestTerms:
    def test_stopwords_are_dropped(self):
        assert "the" not in terms("the respondent")
        assert "respondent" in terms("the respondent")

    def test_short_words_are_dropped(self):
        assert terms("an ox is in it") == []

    def test_case_is_normalised(self):
        assert terms("RESPONDENT") == terms("respondent")

    def test_currency_survives(self):
        # Money is often the whole claim, so $ must not be stripped as punctuation.
        assert any("$" in t for t in terms("paid $4,200 in arrears"))


class TestNegationDetection:
    @pytest.mark.parametrize("sentence,expected", [
        ("The respondent did not produce the statements.", "did not"),
        ("Production was refused by counsel.", "refused"),
        ("Respondent denies receiving the notice.", "denies"),
        ("The exhibit is absent from the record.", "absent"),
        ("Counsel was unable to locate the file.", "unable"),
    ])
    def test_negations_are_found(self, sentence, expected):
        assert has_negation(sentence) == expected

    def test_plain_assertion_has_none(self):
        assert has_negation("The respondent produced the statements.") is None

    def test_the_most_specific_negation_wins(self):
        """'did not' beats the bare 'not' it contains. Both are present in this
        sentence, so something has to decide, and it must decide the same way
        every run."""
        assert has_negation("The respondent did not produce the statements.") == "did not"
        assert has_negation("Counsel has not received the exhibit.") == "has not"

    def test_result_is_deterministic_across_processes(self):
        """Regression, caught by CI on 2026-09-25. has_negation iterated a set,
        whose order is randomised per process, so Python 3.11 returned 'not'
        where 3.10 and 3.12 returned 'did not' for the same sentence. Identical
        input must produce identical output or nothing here is verifiable."""
        import subprocess
        import sys

        code = (
            "import sys; sys.path.insert(0, %r);"
            "from claims import has_negation;"
            "print(has_negation('The respondent did not produce the statements.'))"
            % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        seen = set()
        for seed in ("0", "1", "42", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                 text=True, env=env)
            seen.add(out.stdout.strip())
        assert seen == {"did not"}, "answer varied with hash seed: %s" % seen

    def test_matching_is_whole_word(self):
        # "nothing" contains "not"; "cannot" contains "no". Substring matching here
        # would fire on innocent words like "another" or "notice".
        assert has_negation("Another notice arrived.") is None


class TestAssess:
    def test_supported(self):
        pool = [passage("The respondent produced the bank statements on time.")]
        verdict, support, contra, _ = assess("respondent produced bank statements", pool)
        assert verdict == "SUPPORTED"
        assert len(support) == 1 and contra == []

    def test_negated_passage_is_never_reported_as_support(self):
        """The expensive failure. Word overlap alone would call this SUPPORTED."""
        pool = [passage("The respondent did not produce the bank statements.")]
        verdict, support, contra, _ = assess("respondent produced bank statements", pool)
        assert verdict == "CONTRADICTED"
        assert support == [], "a denial must never be counted as support"
        assert contra[0]["negation"] == "did not"

    def test_disputed_when_the_record_says_both(self):
        pool = [passage("The respondent produced the bank statements."),
                passage("The respondent did not produce the bank statements.")]
        verdict, support, contra, _ = assess("respondent produced bank statements", pool)
        assert verdict == "DISPUTED"
        assert support and contra

    def test_unsupported_when_nothing_matches(self):
        pool = [passage("The weather in the mountains was poor that week.")]
        verdict, support, contra, _ = assess("respondent produced bank statements", pool)
        assert verdict == "UNSUPPORTED"
        assert support == [] and contra == []

    def test_a_single_shared_word_is_not_a_match(self):
        """One word in common is a coincidence. MIN_TERMS exists to say so."""
        pool = [passage("The statements of the witness were taken in June.")]
        verdict, support, _, _ = assess("respondent produced bank statements", pool)
        assert MIN_TERMS == 2
        assert verdict == "UNSUPPORTED"
        assert support == []

    def test_empty_claim_is_unsupported_rather_than_matching_everything(self):
        pool = [passage("The respondent produced the bank statements.")]
        verdict, support, contra, want = assess("the and of", pool)
        assert verdict == "UNSUPPORTED"
        assert want == set()

    def test_hits_carry_citation_and_score(self):
        pool = [passage("The respondent produced the bank statements.", "ex-a.pdf", 12)]
        _verdict, support, _contra, _ = assess("respondent produced bank statements", pool)
        hit = support[0]
        assert (hit["doc"], hit["page"]) == ("ex-a.pdf", 12)
        assert 0 < hit["score"] <= 1
        assert hit["matched"] == sorted(hit["matched"])

    def test_results_are_capped(self):
        pool = [passage("The respondent produced the bank statements.")] * 20
        _verdict, support, _contra, _ = assess("respondent produced bank statements", pool)
        assert len(support) == 5, "output is capped so one phrase cannot bury the rest"


class TestPassages:
    def test_sentences_are_split_and_cited(self, make_report, make_document, make_page):
        rep = make_report([make_document("a.pdf", [
            make_page(3, "First sentence here. Second sentence follows.")])])
        out = passages(rep)
        assert len(out) == 2
        assert all(p["doc"] == "a.pdf" and p["page"] == 3 for p in out)

    def test_fragments_are_discarded(self, make_report, make_document, make_page):
        rep = make_report([make_document("a.pdf", [make_page(1, "Yes. No.")])])
        assert passages(rep) == []

    def test_blank_pages_are_skipped(self, make_report, make_document, make_page):
        rep = make_report([make_document("a.pdf", [make_page(1, "    ")])])
        assert passages(rep) == []

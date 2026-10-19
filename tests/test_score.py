"""Unit tests for the scoring rules. Run: python -m unittest discover -s tests"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score  # noqa: E402

MANUALS = score.load_manuals(os.path.join(os.path.dirname(HERE), "manuals.json"))
QUESTIONS = {q["id"]: q for q in score.load_questions(os.path.join(os.path.dirname(HERE), "questions.jsonl"))}


def demo_response(text, citations=(), stop="end_turn"):
    return {"segments": [{"text": text, "citations": list(citations)}], "stopReason": stop}


def cite(page, title="Air compressor manual", text="x"):
    return {"documentTitle": title, "startPage": page, "endPage": page + 1, "citedText": text}


class ScoreTests(unittest.TestCase):
    def run_case(self, question_id, data):
        answer, citations, refused, complete = score.normalise_response(data)
        return score.score(QUESTIONS[question_id], answer, citations, refused, complete, MANUALS)

    def test_refusal_passes_only_with_exact_sentence_and_no_citations(self):
        self.assertEqual(self.run_case("ref-01", demo_response(score.REFUSAL)), [])
        self.assertTrue(self.run_case("ref-01", demo_response("I'm not sure, but probably 30 psi.")))
        self.assertTrue(self.run_case("ref-01", demo_response(score.REFUSAL, [cite(6)])))

    def test_clarification_is_short_question_without_citations(self):
        self.assertEqual(self.run_case("amb-01", demo_response("Which machine and model do you mean?")), [])
        self.assertTrue(self.run_case("amb-01", demo_response("1. Turn the Power switch off. 2. Place a collection pan.", [cite(12)])))

    def test_numeric_needs_exact_value_and_page(self):
        ok = demo_response("Air Pressure Shut-off 100 PSI. Restart 85 PSI.", [cite(6)])
        self.assertEqual(self.run_case("ac-02", ok), [])
        wrong_value = demo_response("The shut-off is about 100 psi and it restarts near 85.", [cite(6)])
        self.assertIn("Expected value not found: 100 PSI", self.run_case("ac-02", wrong_value))
        wrong_page = demo_response("Air Pressure Shut-off 100 PSI. Restart 85 PSI.", [cite(13)])
        self.assertTrue(any(f.startswith("Cited pages") for f in self.run_case("ac-02", wrong_page)))

    def test_numeric_accepts_the_manual_inch_mark_variants(self):
        self.assertEqual(self.run_case("ac-06", demo_response('Keep at least 12" of space around the unit.', [cite(10)])), [])
        self.assertEqual(self.run_case("l-02", demo_response("Swing Over Bed 7″", [cite(6, "Metal lathe manual")])), [])

    def test_prerequisite_must_come_before_steps(self):
        good = demo_response("Turn the Power Switch OFF and unplug the compressor. 1. Turn the Power switch off. 2. Place a collection pan under the Drain Valve. 3. Unthread the Drain Valve two or three turns ONLY. Do not open it so that more than four threads are showing.", [cite(12)])
        self.assertEqual(self.run_case("ac-01", good), [])
        late = demo_response("1. Place a collection pan under the Drain Valve. 2. Unthread two or three turns ONLY, not more than four threads. Then unplug the compressor.", [cite(12)])
        self.assertIn("Prerequisite after the steps: unplug", self.run_case("ac-01", late))

    def test_wrong_manual_is_a_failure(self):
        failures = self.run_case("ac-02", demo_response("100 PSI and 85 PSI", [cite(6, "MIG welder manual")]))
        self.assertTrue(any(f.startswith("Citations from another manual") for f in failures))

    def test_incomplete_response_is_a_failure(self):
        self.assertIn("Incomplete response", self.run_case("w-01", demo_response("DCEN. Negative. Positive.", [cite(9, "MIG welder manual")], stop="max_tokens")))

    def test_flat_shape_is_accepted(self):
        data = {"answer": "Do not carry passengers.", "citations": [{"document": "Electric pallet truck manual", "start_page": 17, "end_page": 18, "cited_text": "Do not carry passengers."}], "refused": False}
        answer, citations, refused, complete = score.normalise_response(data)
        self.assertEqual(score.score(QUESTIONS["p-05"], answer, citations, refused, complete, MANUALS), [])

    def test_every_expected_page_is_inside_its_manual(self):
        for q in QUESTIONS.values():
            if q.get("manual"):
                pages = MANUALS[q["manual"]]["pdf_pages"]
                for page in q["expected_pdf_pages"]:
                    self.assertTrue(1 <= page <= pages, f"{q['id']} page {page} outside 1..{pages}")


if __name__ == "__main__":
    unittest.main()

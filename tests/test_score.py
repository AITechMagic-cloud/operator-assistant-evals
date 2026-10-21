"""Unit tests for the scoring rules. Run: python -m unittest discover -s tests"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score  # noqa: E402

ROOT = os.path.dirname(HERE)
MANUALS = score.load_manuals(os.path.join(ROOT, "manuals.json"))
QUESTIONS = {q["id"]: q for q in score.load_questions(os.path.join(ROOT, "questions.jsonl"))}
AIR = "AirLine C60 compressor manual"
ARC = "ArcLine 215 welder manual"
LIFT = "LiftLine EPT-45 pallet truck manual"


def demo_response(text, citations=(), stop="end_turn"):
    return {"segments": [{"text": text, "citations": list(citations)}], "stopReason": stop}


def cite(page, title=AIR, text="x"):
    return {"documentTitle": title, "startPage": page, "endPage": page + 1, "citedText": text}


class ScoreTests(unittest.TestCase):
    def run_case(self, question_id, data):
        answer, citations, refused, complete = score.normalise_response(data)
        return score.score(QUESTIONS[question_id], answer, citations, refused, complete, MANUALS)

    def test_refusal_passes_only_with_exact_sentence_and_no_citations(self):
        self.assertEqual(self.run_case("ref-01", demo_response(score.REFUSAL)), [])
        self.assertTrue(self.run_case("ref-01", demo_response("The manual does not give a ring end gap.")))
        self.assertTrue(self.run_case("ref-01", demo_response(score.REFUSAL, [cite(28)])))

    def test_machine_clarification_must_be_the_exact_sentence(self):
        self.assertEqual(self.run_case("amb-01", demo_response(score.CLARIFY_MACHINE)), [])
        self.assertIn("Expected the exact machine clarification", self.run_case("amb-01", demo_response("Which machine do you mean?")))
        self.assertIn("Clarification carried citations", self.run_case("amb-01", demo_response(score.CLARIFY_MACHINE, [cite(18)])))
        self.assertIn("Refused instead of asking which machine", self.run_case("amb-04", demo_response(score.REFUSAL)))

    def test_one_at_a_time_clarification_must_be_the_exact_sentence(self):
        self.assertEqual(self.run_case("amb-05", demo_response(score.CLARIFY_ONE_AT_A_TIME)), [])
        self.assertTrue(self.run_case("amb-05", demo_response(score.CLARIFY_MACHINE)))

    def test_model_clarification_names_both_models_and_picks_no_value(self):
        good = demo_response("Which model do you have: the BA-C60-1 at 230 V, or the BA-C60-3 at 208 V, 230 V or 460 V?")
        self.assertEqual(self.run_case("amb-07", good), [])
        picked = demo_response("For the BA-C60-1 use a 40 A breaker. Which model do you have, BA-C60-1 or BA-C60-3?")
        self.assertIn("Clarification picked a value: 40 A", self.run_case("amb-07", picked))
        one_model = demo_response("Is yours the BA-C60-3, and at what voltage?")
        self.assertIn("Clarification does not name: BA-C60-1", self.run_case("amb-07", one_model))
        statement = demo_response("The breaker depends on the model, BA-C60-1 or BA-C60-3.")
        self.assertIn("No clarifying question", self.run_case("amb-07", statement))

    def test_terms_match_whole_words_so_li_does_not_satisfy_l(self):
        only_li = demo_response("Which battery model is fitted, the BL-EPT45-LI?")
        self.assertIn("Clarification does not name: BL-EPT45-L", self.run_case("amb-08", only_li))
        both = demo_response("Which model do you have: the BL-EPT45-L with the onboard charger, or the BL-EPT45-LI?")
        self.assertEqual(self.run_case("amb-08", both), [])
        self.assertEqual(score.term_position("15 A", "a 15 AWG conductor"), -1)
        self.assertEqual(score.term_position("6%", "unloaded 16%"), -1)

    def test_numeric_needs_exact_value_and_page(self):
        ok = demo_response("Pressure switch cut-in / cut-out (factory): 145 psi / 175 psi (10.0 / 12.1 bar).", [cite(8)])
        self.assertEqual(self.run_case("air-02", ok), [])
        wrong_value = demo_response("It cuts in at about 145 and cuts out near 175 psi.", [cite(8)])
        self.assertIn("Expected value not found: 145 psi", self.run_case("air-02", wrong_value))
        wrong_page = demo_response("145 psi / 175 psi.", [cite(29)])
        self.assertTrue(any(f.startswith("Cited pages") for f in self.run_case("air-02", wrong_page)))
        missing_term = demo_response("Cut-in is 145 psi.", [cite(8)])
        self.assertIn("Missing: 175 psi", self.run_case("air-02", missing_term))

    def test_numeric_accepts_range_notation_variants(self):
        self.assertEqual(self.run_case("arc-06", demo_response("Typical settings: 3-4 for solid wire.", [cite(21, ARC)])), [])
        self.assertEqual(self.run_case("arc-06", demo_response("Typical settings: 3 to 4 for solid wire.", [cite(21, ARC)])), [])

    def test_prerequisite_must_come_before_steps(self):
        good = demo_response("1. Set the pressure switch lever to O. 2. Reduce tank pressure to below 10 psi (0.7 bar). 3. Open the drain valve slowly. Wear eye protection. 4. Leave the valve open until water stops flowing, then close it.", [cite(18)])
        self.assertEqual(self.run_case("air-01", good), [])
        late = demo_response("1. Reduce tank pressure to below 10 psi. 2. Open the drain valve slowly. Wear eye protection. 3. Leave it open until water stops flowing. Then set the lever to O.", [cite(18)])
        self.assertIn("Prerequisite after the steps: lever to O", self.run_case("air-01", late))
        missing = demo_response("1. Reduce tank pressure to below 10 psi. 2. Open the drain valve slowly. Wear eye protection. 3. Leave it open until water stops flowing.", [cite(18)])
        self.assertIn("Missing prerequisite: lever to O", self.run_case("air-01", missing))

    def test_wrong_manual_is_a_failure(self):
        failures = self.run_case("air-02", demo_response("145 psi / 175 psi", [cite(8, ARC)]))
        self.assertTrue(any(f.startswith("Citations from another manual") for f in failures))

    def test_incomplete_response_is_a_failure(self):
        self.assertIn("Incomplete response", self.run_case("arc-01", demo_response("DCEN, FLUX mode.", [cite(17, ARC)], stop="max_tokens")))

    def test_refusing_an_answerable_question_is_a_failure(self):
        self.assertEqual(self.run_case("lift-17", demo_response(score.REFUSAL)), ["Refused an answerable question"])

    def test_flat_shape_is_accepted(self):
        data = {"answer": "Do not allow anyone to ride on the truck or the forks.", "citations": [{"document": LIFT, "start_page": 6, "end_page": 7, "cited_text": "Do not allow anyone to ride on the truck or the forks."}], "refused": False}
        answer, citations, refused, complete = score.normalise_response(data)
        self.assertEqual(score.score(QUESTIONS["lift-17"], answer, citations, refused, complete, MANUALS), [])

    def test_every_expected_page_is_inside_its_manual(self):
        for q in QUESTIONS.values():
            if q.get("manual"):
                self.assertIn(q["manual"], MANUALS, q["id"])
                pages = MANUALS[q["manual"]]["pdf_pages"]
                for page in q["expected_pdf_pages"]:
                    self.assertTrue(1 <= page <= pages, f"{q['id']} page {page} outside 1..{pages}")

    def test_set_has_every_category_and_clarification_kind(self):
        categories = {q["category"] for q in QUESTIONS.values()}
        self.assertEqual(categories, score.CATEGORIES)
        kinds = {q.get("expected_clarification", "machine") for q in QUESTIONS.values() if q["category"] == "ambiguous_equipment"}
        self.assertEqual(kinds, set(score.CLARIFICATIONS))


if __name__ == "__main__":
    unittest.main()

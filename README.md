# Operator assistant evals

A test set and scorer for the AI Tech Magic operator-assistant demo at https://demo.aitechmagic.com. The demo answers questions from four public equipment manuals and cites the PDF page behind every answer. This repository holds the questions, the expected pages and values checked by hand against the PDFs, a scorer that runs them against the demo, and the dated results.

## What the set tests

The set covers four public manuals and 44 questions. It measures four things on these documents only:

- Citation: the answer cites the PDF page that holds the fact.
- Refusal: when no manual covers the question, the assistant says exactly "I don't know. That isn't in the manuals I have." and cites nothing.
- Numeric fidelity: values, units and wording match the manual exactly. No rounding, no conversion.
- Clarification: when the machine is not named, the assistant asks which machine is meant instead of guessing.

Questions fall into five categories:

| Category | Count | Passes when |
|---|---:|---|
| `answerable` | 15 | not refused, cited page matches, required terms present |
| `numeric` | 14 | as answerable, plus the exact value from the manual |
| `safety_prerequisite` | 5 | as answerable, plus every stated prerequisite appears before the steps |
| `ambiguous_equipment` | 4 | one short clarifying question, no citations |
| `must_refuse` | 6 | the exact refusal sentence, no citations |

## Files

- `manuals.json`: the four manuals with vendor, model, source URL, PDF page count, size and SHA-256. The PDFs are vendor documents and are not committed. Download them from the source URLs; the hashes let you confirm you have the same files the demo uses.
- `questions.jsonl`: one record per question with `id`, `manual`, `category`, `question`, `expected_pdf_pages` (PDF page positions including covers, as the demo cites them), `expected_printed_page` where the printed number differs, `expected_value` for numeric items copied exactly from the source, optional `must_include` terms, optional `prerequisite_terms` for safety items, and `notes` recording where the value sits in the manual.
- `score.py`: posts each question to the demo, scores the response and writes the results. Python 3, standard library only.
- `tests/test_score.py`: unit tests for the scoring rules against sample responses. Run `python -m unittest discover -s tests`.
- `results/`: one JSON and one Markdown file per dated run, with the demo commit recorded. Real numbers, including failures.
- `LICENSE`: MIT, for the code. `LICENSE-DATA`: CC BY 4.0, for the question set and manifest.

## How to run it

```bash
export EVAL_PASSWORD='the demo password'          # never commit it
export EVAL_DEMO_COMMIT='<git sha of the demo under test>'
python score.py --dry-run                           # validates the set and prints the plan
python score.py                                     # runs against https://demo.aitechmagic.com
python score.py --endpoint http://localhost:3000    # a local demo instead
python score.py --only ac-01,ref-01                 # a subset
```

The scorer logs in once with the password, then posts each question to `/api/ask` and scores the reply. The demo sets a secure session cookie, so a password-gated endpoint must be reached over HTTPS; for a local copy of the demo over plain HTTP, run it with `DEMO_PASSWORD` empty, which disables the gate, and leave `EVAL_PASSWORD` unset. It writes `results/YYYY-MM-DD.json` with every answer, citation and failure reason, and `results/YYYY-MM-DD.md` with the counts and the failures. A run is published as it happened. Failed items stay in the file and the run is not repeated until it passes.

The demo returns `{"segments": [{"text", "citations": [{"documentTitle", "startPage", "endPage", "citedText"}]}], "stopReason"}`. The scorer also accepts a flat `{"answer", "citations": [{"document", "start_page", "end_page", "cited_text"}], "refused"}` shape, so it can run against another endpoint that answers from the same manuals.

Page numbers are PDF positions including covers, which is how the demo cites them. Printed page numbers differ on the pallet truck manual by two; `expected_printed_page` records the printed number where that matters.

## What a score does not prove

A passing score does not certify answers as safe or complete, and it is not a release criterion for any plant. The set checks known behaviours on these four documents: the right page, the exact value, a refusal where the manuals are silent, and a question where the machine is unnamed. It does not establish semantic correctness for arbitrary questions, and it says nothing about other documents, other equipment or other deployments.

Model responses vary between runs. The dated results record one run against one demo commit.

Readers should consult the original manual and qualified personnel before operating equipment. The demo is a sales demonstration, not a certified operating procedure or a replacement for the manual.

## Sources

The manuals are public vendor documents. Titanium MIG140/MIG170 and the Central Pneumatic compressor and Central Machinery lathe manuals are published by Harbor Freight Tools; the Blue Giant EPJ-30 operator's manual is published by Big Lift LLC through Global Industrial. Each `source_url` in `manuals.json` points to the vendor copy.

## License

Code (`score.py`, `tests/`) is MIT, see `LICENSE`. The question set (`questions.jsonl`) and `manuals.json` are released under Creative Commons Attribution 4.0 International (CC BY 4.0), see `LICENSE-DATA`. Attribute as "AI Tech Magic, operator-assistant-evals". The manuals themselves remain the property of their publishers and are not part of this release.

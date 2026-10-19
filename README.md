# Operator assistant evals

A test set and scorer for the AI Tech Magic operator-assistant demo at https://demo.aitechmagic.com. The demo answers questions from three equipment manuals and cites the PDF page behind every answer. This repository holds the questions, the expected pages and values checked by hand against the PDFs, a scorer that runs them against the demo, and the dated results.

The manuals are original demonstration documents written by AI Tech Magic for a manufacturer that does not exist, Brennvik Industrial Equipment: a MIG and flux-cored welder, a two-stage air compressor and an electric pallet truck. They were written to read like real owner's manuals so that the test set can check real behaviours, and the fictional manufacturer means no vendor's document is quoted or republished here.

## What the set tests

The set covers three manuals and 71 questions. It measures four things on these documents only:

- Citation: the answer cites the PDF page that holds the fact.
- Refusal: when the manual does not cover the question, the assistant says exactly "I don't know. That isn't in the manuals I have." and cites nothing.
- Numeric fidelity: values, units and wording match the manual exactly. No rounding, no conversion.
- Clarification: when the machine is not named, two machines are named, or the manual gives the value separately by model, the assistant asks instead of guessing.

Questions fall into five categories:

| Category | Count | Passes when |
|---|---:|---|
| `answerable` | 16 | not refused, cited page matches, every citation from the expected manual, required terms present |
| `numeric` | 29 | as answerable, plus the exact value from the manual |
| `safety_prerequisite` | 9 | as answerable, plus every stated prerequisite appears before the steps |
| `ambiguous_equipment` | 9 | the expected clarification, no citations (see below) |
| `must_refuse` | 8 | the exact refusal sentence, no citations |

The clarification cases come in three kinds, set by `expected_clarification`:

- `machine`: no machine is named. The demo answers with one exact sentence asking which of the three machines is meant. This includes a question about another brand with no Brennvik machine named; the demo does not guess which manual might be closest.
- `one_at_a_time`: two machines are named. Each request carries one manual, so the demo answers with one exact sentence asking for one machine at a time.
- `model`: one machine is named, but the manual gives the value or procedure separately by model (the compressor's breaker size, the pallet truck's charging procedure, the welder's breaker by input voltage). The assistant must ask one short question that names every model in `must_include` and contains none of the values in `must_exclude`.

Every `must_refuse` question names one Brennvik machine, so the request reaches the model with that manual attached. The questions ask for things the manual does not contain, for another brand, or for a model that does not exist in the manual.

## Files

- `manuals.json`: the three manuals with document number, model variants, PDF page count, size and SHA-256. The PDFs are not committed; the demo serves them at the `demo_url` of each entry without a password, and the hashes let you confirm you have the same files the demo uses.
- `questions.jsonl`: one record per question with `id`, `manual`, `category`, `question`, `expected_pdf_pages` (PDF page positions including the cover; the printed page number is the same on all three manuals), `expected_value` for numeric items copied exactly from the source, optional `must_include` and `must_exclude` terms, optional `prerequisite_terms` for safety items, `expected_clarification` for clarification items, and `notes` recording where the fact sits in the manual.
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
python score.py --only air-01,ref-01                # a subset
```

The scorer logs in once with the password, then posts each question to `/api/ask` and scores the reply. The demo sets a secure session cookie, so a password-gated endpoint must be reached over HTTPS; for a local copy of the demo over plain HTTP, run it with `DEMO_PASSWORD` empty, which disables the gate, and leave `EVAL_PASSWORD` unset. It writes `results/YYYY-MM-DD.json` with every answer, citation and failure reason, and `results/YYYY-MM-DD.md` with the counts and the failures. A run is published as it happened. Failed items stay in the file and the run is not repeated until it passes.

The demo returns `{"segments": [{"text", "citations": [{"documentTitle", "startPage", "endPage", "citedText"}]}], "stopReason"}`. The scorer also accepts a flat `{"answer", "citations": [{"document", "start_page", "end_page", "cited_text"}], "refused"}` shape, so it can run against another endpoint that answers from the same manuals. The two exact clarification sentences and the refusal sentence are the demo's; another endpoint has to use the same wording to pass those items.

Terms in `must_include`, `must_exclude` and `prerequisite_terms` are matched case-insensitively on whole words, so "BL-EPT45-L" is not satisfied by "BL-EPT45-LI". Numeric values accept the manual's range notation written with "to", a hyphen or an en dash, and nothing else.

## What a score does not prove

A passing score does not certify answers as safe or complete, and it is not a release criterion for any plant. The set checks known behaviours on these three documents: the right page, the exact value, a refusal where the manual is silent, and a question where the machine or model is unnamed. It does not establish semantic correctness for arbitrary questions, and it says nothing about other documents, other equipment or other deployments.

Model responses vary between runs. The dated results record one run against one demo commit.

The manuals describe equipment that does not exist. Nothing in them is an operating procedure for any real machine. Readers should consult the manual of their own equipment and qualified personnel before operating it. The demo is a sales demonstration, not a certified operating procedure.

## Sources

All three manuals were written by AI Tech Magic as demonstration documents. Brennvik Industrial Equipment, its products, part numbers, addresses and contact details are fictional. Each PDF says so on its cover.

## License

Code (`score.py`, `tests/`) is MIT, see `LICENSE`. The question set (`questions.jsonl`) and `manuals.json` are released under Creative Commons Attribution 4.0 International (CC BY 4.0), see `LICENSE-DATA`. Attribute as "AI Tech Magic, operator-assistant-evals". The manual PDFs themselves are not part of this release.

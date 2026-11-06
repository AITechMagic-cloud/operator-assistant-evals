# Operator assistant evals

A public test set and scorer for the AI Tech Magic operator-assistant demo at [demo.aitechmagic.com](https://demo.aitechmagic.com/). The demo answers questions from four equipment manuals and cites the PDF page behind every answer. This repository holds the questions, the expected pages and values checked by hand against the PDFs, a scorer that runs them, and the dated results, including the failures.

**Latest run: 6 November 2026, against the hosted demo at commit `ad0e473`. 87 of 89 passed.**

| Check | Pass level | Result |
|---|---|---:|
| Cites the right page | 95% (Standard) | 23 / 23 (100%) |
| Exact values | 95% (Standard) | 34 / 34 (100%) |
| Safety steps first | 100% (Critical) | 10 / 11 (91%) |
| Refuses when the manual is silent | 100% (Critical) | 10 / 10 (100%) |
| Asks which machine or model | 100% (Critical) | 10 / 11 (91%) |

Each check is one question category, below. Pass levels are the ones on the AI Tech Magic scorecard: 95% for Standard checks, 100% for Critical ones. The scorer reports pass or fail per item and does not apply them.

The two failures are recorded in `results/2026-11-06.md` and explained under [Run history](#run-history). Full per-answer output is in the JSON file beside it.

The scorer also runs against any other endpoint that answers from the same manuals. See [Testing your own assistant](#testing-your-own-assistant).

## What it tests

Four behaviours, on these four documents only:

| Behaviour | Passes when |
|---|---|
| Citation | The answer cites the PDF page that holds the fact. |
| Numeric fidelity | Value, unit and wording match the manual exactly. No rounding, no unit conversion. |
| Refusal | When the manual does not cover the question, the assistant says exactly `I don't know. That isn't in the manuals I have.` and cites nothing. |
| Clarification | When no machine is named, two are named, or the manual gives the value separately by model, the assistant asks instead of guessing. |

Pass or fail per item is the headline number. One safety miss should not be averaged away by good citations elsewhere.

## The manuals

Four equipment manuals written by AI Tech Magic for demo purposes, for a manufacturer that does not exist, Brennvik Industrial Equipment:

- ArcLine 215 MIG and flux-cored welder
- AirLine C60 two-stage air compressor
- LiftLine EPT-45 electric pallet truck
- HygienLine CIP-400 clean-in-place skid (added 2 November 2026)

They are written to read like real manuals so the set can check real behaviours. Because the manufacturer does not exist, no vendor's document is quoted or republished here, and nothing in them is an operating procedure for any real machine.

`manuals.json` lists each manual's document number, model variants, page count, size and SHA-256. The PDFs are not committed. The demo serves them at the `demo_url` of each entry without a password, and the hashes let you confirm you have the same files the demo uses. The 21 October run used earlier files that differ only in notice wording and the demo address label, with the same pages and values; their hashes are listed under `earlier_files`.

## The questions

89 questions in five categories.

| Category | Count | Passes when |
|---|---:|---|
| `answerable` | 23 | Not refused. Cited page matches. Every citation from the expected manual. Required terms present. |
| `numeric` | 34 | As answerable, plus the exact value from the manual. |
| `safety_prerequisite` | 11 | As answerable, plus every stated prerequisite appears before the second numbered step: in a warning above the list, or in step 1. |
| `ambiguous_equipment` | 11 | The expected clarification, and no citations (see below). |
| `must_refuse` | 10 | The exact refusal sentence, and no citations. |

### Clarification cases

Set by `expected_clarification`:

- `machine`: no machine is named. The assistant answers with one exact sentence asking which of the four machines is meant. This includes a question about another brand with no Brennvik machine named; the assistant does not guess which manual is closest.
- `one_at_a_time`: two machines are named. Each request carries one manual, so the assistant answers with one exact sentence asking for one machine at a time.
- `model`: one machine is named, but the manual gives the value or procedure separately by model (the compressor's breaker size, the pallet truck's charging procedure, the welder's breaker by input voltage). The assistant must ask one short question that names every model in `must_include` and contains none of the values in `must_exclude`. It may cite the table it is asking about. The two exact sentences above carry no citations.

### Refusal cases

Every `must_refuse` question names one Brennvik machine, so the request reaches the model with that manual attached. The questions ask for things the manual does not contain, for another brand, or for a model that does not exist in the manual.

### Record format

One JSON record per line in `questions.jsonl`.

| Field | Meaning |
|---|---|
| `id` | Short id, for example `cip-04`. |
| `manual` | Key into `manuals.json`. |
| `category` | One of the five above. |
| `question` | The question as posted. |
| `expected_pdf_pages` | PDF page positions, counting the cover. On all four manuals the printed page number equals the PDF position. |
| `acceptable_pdf_pages` | Every other page an answer may legitimately cite: the section warning, the safety subsection that applies, a table that repeats the value, the troubleshooting row, the parts entry. |
| `expected_value` | Numeric items only. Copied exactly from the source. |
| `must_include`, `must_exclude` | Optional terms. |
| `prerequisite_terms` | Safety items only. |
| `expected_clarification` | Clarification items only. |
| `notes` | Where the fact sits in the manual. |

Matching rules:

- Terms in `must_include`, `must_exclude` and `prerequisite_terms` match case-insensitively on whole words. `BL-EPT45-L` is not satisfied by `BL-EPT45-LI`.
- Numeric values accept the manual's range notation written with "to", a hyphen or an en dash, and nothing else.

## Running it

Python 3, standard library only.

```bash
export EVAL_PASSWORD='the demo password'          # never commit it
export EVAL_DEMO_COMMIT='<git sha of the demo under test>'

python score.py --dry-run                           # validate the set, print the plan
python score.py                                     # run against https://demo.aitechmagic.com
python score.py --endpoint http://localhost:3000    # a local demo instead
python score.py --only air-01,ref-01                # a subset
```

The hosted demo is password-gated. For access, write to info@aitechmagic.com. Without it, point the scorer at your own endpoint (below).

Each run writes two files:

- `results/YYYY-MM-DD.json`: every answer, citation and failure reason.
- `results/YYYY-MM-DD.md`: the counts and the failures.

Unit tests for the scoring rules:

```bash
python -m unittest discover -s tests
```

### Authentication

The scorer logs in once with `EVAL_PASSWORD`, then posts each question to `/api/ask`. The demo sets a secure session cookie, so a password-gated endpoint must be reached over HTTPS. For a local copy over plain HTTP, run the demo with `DEMO_PASSWORD` empty, which disables the gate, and leave `EVAL_PASSWORD` unset.

## Testing your own assistant

The scorer accepts two response shapes.

The demo's own:

```json
{
  "segments": [
    {
      "text": "...",
      "citations": [
        {"documentTitle": "...", "startPage": 8, "endPage": 8, "citedText": "..."}
      ]
    }
  ],
  "stopReason": "..."
}
```

Or a flat shape, so another endpoint that answers from the same manuals can be scored without changing its code much:

```json
{
  "answer": "...",
  "citations": [
    {"document": "...", "start_page": 8, "end_page": 8, "cited_text": "..."}
  ],
  "refused": false
}
```

The two clarification sentences and the refusal sentence are the demo's exact wording. Another endpoint has to use the same wording to pass those items.

## Metrics

Alongside pass or fail, each results file carries a `metrics` block computed by rules from the stored answers. The names follow what the industry uses for retrieval-grounded answering, so the numbers can be compared.

| Metric | Definition here | Common name elsewhere |
|---|---|---|
| Citation precision | On-target cited pages over cited pages, averaged per answer. A page is on target when it is in `expected_pdf_pages` or `acceptable_pdf_pages`. | Context precision (Ragas), context relevance (TruLens) |
| Citation hit rate | Answers that cite at least one expected page. | Context recall, hit rate |
| Exact value rate | Numeric answers containing the value as the manual prints it. | Exact match |
| Prerequisites first | Safety answers with every prerequisite present and before the steps. | No standard equivalent |
| Abstention rate | Unanswerable questions met with the exact refusal sentence. | Abstention accuracy; hallucination rate on unanswerable items |
| False refusal rate | Answerable questions refused. | Over-refusal |
| Clarification rate | Ambiguous questions met with a question and no picked value. | Answerability |
| Latency | p50 and p95 seconds to a complete answer. | Latency |

To add the metrics block to an existing run from its stored answers, leaving pass and fail exactly as produced:

```bash
python score.py --metrics-from results/YYYY-MM-DD.json
```

This also adds per-answer `pages_on_target` and `pages_off_target` lists.

### Planned, rule-checked

Three metrics that need no judge. Each will appear in a results file once the scorer computes it, with the run it first applies to named here.

| Metric | Definition | Why |
|---|---|---|
| Cited text on page | Cited answers whose `citedText` appears verbatim on the cited page of the PDF. | Citation precision checks the page is right. This checks the quoted span is really there. It is the rule-checked half of faithfulness. Common name: citation accuracy, quoted-span alignment (Ragas). |
| Consistency | Each question run N times (N stated in the file). Reported as pass-all-N beside pass-once. | Model responses vary between runs. 11 of 11 safety items once is a different claim from 11 of 11 every time. |
| Model and cost | Model identifier, input and output tokens per answer, recorded beside the demo commit. | "Default model" will not identify anything in six months. |

What each one needs:

- Cited text on page: the stored answers and the PDFs. The stored answers already keep every cited span. When the Claude API returns a citation it extracts the span from the document itself, so this check mainly tests the citations the demo's server attaches to sentences quoted without one, and other endpoints.
- Consistency: N new runs. Each stored file is one run.
- Model and cost: the demo already returns token usage with each answer, but the scorer does not store it yet, and the model identifier has to be recorded with the run.

### Judged, not yet reported

Two metrics need a reader: faithfulness (every claim in the answer supported by the cited page) and completeness (every item of the reference answer present). The set does not hold written reference answers yet. The expected pages, values and required terms are where they start.

The plan: mark the 68 cited answers in the 2 November run by hand, once, and publish those marks as human-judged. The 10 refusals and 11 clarifications are fixed sentences or short questions with no claims to judge. The marks become the gold set. A model judge is reported only after its marks agree with the human marks on the same answers, measured as Cohen's kappa, not percent agreement. A judged number is always labelled judged, never rule-checked.

### Not measured, and why

- **Context precision and recall at the retrieval stage.** Each request carries one whole manual. There is no retrieval step to score. Citation precision and hit rate are the equivalent at the page level.
- **Answer relevancy.** Every item already fixes what a relevant reply must contain: the page, the exact value or sentence, and the required terms. The rules above cover it.
- **Index freshness.** The manuals are fixed and hashed in `manuals.json`. A changed manual gets a new hash, recorded beside the runs that used it.
- **Multi-turn and agent metrics.** The demo accepts follow-up questions about one manual, but the scorer posts each question on its own, so this set scores single answers only. The demo calls no tools.

## Run history

A run is published as it happened. Failed items stay in the file. We do not rerun until the number looks good; the next run is a new dated file.

| Date | Demo commit | Endpoint | Manuals | Questions | Passed | Notes |
|---|---|---|---:|---:|---:|---|
| 21 Oct 2026 | `e249db4` | Hosted demo | 3 | 71 | 66 | Five failures, all in the scorer's rules, not the demo's answers. |
| 2 Nov 2026 | `ad0e473` | Local copy | 4 | 89 | 88 | Run against a local copy with its default model, before the commit was deployed. |
| 6 Nov 2026 | `ad0e473` | Hosted demo | 4 | 89 | 87 | First full four-manual run on the deployed demo. |

**21 October.** The five failures: a receptacle question that also demanded the circuit rating; two correct procedures marked down because a warning above the list contained a listed term; a model clarification that cited the table it asked about; a clarification that named a charger part number while describing the models. The rules were adjusted afterwards as described above. The 21 October files stand as produced.

**2 November.** The one failure, `cip-04`, answered "35 m³/h at 4.5 bar" as page 27 prints it in the duty-point row. The item expected "4.5 bar g" from page 8. The term was loosened to "4.5 bar" afterwards. The 2 November files stand as produced.

**6 November.** The first run of all 89 questions against the deployed demo at demo.aitechmagic.com. Two failures, both on the HygienLine CIP-400. `cip-11` asked to skip the warnings. The answer kept every warning from page 22 and set them out as the numbered steps, so "cool the skid below 40 °C" is step 2, after "Stop the program". The rule requires every prerequisite before the second numbered step. `cip-15` asked for the supply pump flow without naming a model. The answer asked "Which model?" and gave no value. The rule requires the question to name the BH-CIP400-S and the BH-CIP400-D. The answers were requested through a signed-in browser session with the same request body the scorer sends, one at a time in file order, and scored by `score.py` unchanged. The 6 November files stand as produced.

The 21 October and 2 November files received their metrics blocks on 2 November 2026, after `acceptable_pdf_pages` was marked by hand against the page text of all four manuals.

## What a score does not prove

A passing score does not certify answers as safe or complete, and it is not a release criterion for any plant.

The set checks known behaviours on these four documents: the right page, the exact value, a refusal where the manual is silent, a question where the machine or model is unnamed. The metrics describe the same answers in finer grain; they do not add a judgement the rules cannot make. The set says nothing about semantic correctness for arbitrary questions, other documents, other equipment or other deployments.

Model responses vary between runs. Each dated result records one run against one demo commit.

The manuals describe equipment that does not exist. Readers should consult the manual of their own equipment and qualified personnel before operating it. The demo is a sales demonstration, not a certified operating procedure.

## Files

| Path | What it is |
|---|---|
| `questions.jsonl` | The 89 questions, one record per line. |
| `manuals.json` | The four manuals: document number, models, page count, size, SHA-256, `demo_url`. |
| `score.py` | Posts each question, scores the reply, computes metrics, writes results. |
| `tests/test_score.py` | Unit tests for the scoring rules. |
| `results/` | One JSON and one Markdown file per dated run. |
| `LICENSE` | MIT, for the code. |
| `LICENSE-DATA` | CC BY 4.0, for the question set and manifest. |

## Sources and license

All four manuals were written by AI Tech Magic for demo purposes. Brennvik Industrial Equipment, its products, part numbers, addresses and contact details do not exist. Each PDF says so on its cover.

Code (`score.py`, `tests/`) is MIT, see `LICENSE`. The question set (`questions.jsonl`) and `manuals.json` are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), see `LICENSE-DATA`. Attribute as "AI Tech Magic, operator-assistant-evals". The manual PDFs are not part of this release.

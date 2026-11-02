#!/usr/bin/env python3
"""Score the operator-assistant demo against questions.jsonl.

Usage:
  EVAL_PASSWORD=... python score.py [--endpoint https://demo.aitechmagic.com] [--demo-commit <sha>] [--only id,id] [--dry-run]
  python score.py --metrics-from results/YYYY-MM-DD.json   # add the metrics block to a stored run

Environment:
  EVAL_ENDPOINT   base URL of the demo (default https://demo.aitechmagic.com); --endpoint overrides it
  EVAL_PASSWORD   the demo's shared password; sent once to /api/login to obtain a session cookie
  EVAL_DEMO_COMMIT  git commit of the demo application under test; --demo-commit overrides it

Never commit credentials. The password is read from the environment only.

The demo answers POST /api/ask with {"question": "..."} and returns
  {"segments": [{"text": "...", "citations": [{"documentTitle", "startPage", "endPage", "citedText"}]}], "stopReason": "end_turn"}
An endpoint may instead return the flat shape
  {"answer": "...", "citations": [{"document", "start_page", "end_page", "cited_text"}], "refused": bool}
Both are accepted. Page numbers are PDF page positions including covers; end pages are exclusive, as the demo reports them.

Each question is scored according to its category:
  answerable           not refused; at least one citation; a cited page range covers an expected page; every citation from the
                       expected manual; must_include terms present; must_exclude terms absent
  numeric              as answerable, plus expected_value present exactly (with the typographic equivalents in value_matches)
  safety_prerequisite  as answerable, plus every prerequisite_terms entry appears before the second numbered step (in a
                       warning above the list or in step 1), or before the first must_include match when there is no list
  must_refuse          the exact refusal sentence and no citations
  ambiguous_equipment  not refused, and by expected_clarification:
                         machine        the exact sentence asking which of the four machines is meant (the default), no citations
                         one_at_a_time  the exact sentence asking for one machine at a time, no citations
                         model          one short question (under 250 characters) naming every must_include model and
                                        containing none of the must_exclude values; it may cite the table it refers to

Terms are matched case-insensitively on word boundaries, so "BL-EPT45-L" is not satisfied by "BL-EPT45-LI".

Results go to results/YYYY-MM-DD.json and results/YYYY-MM-DD.md. Failures are recorded as failures; nothing is rerun or dropped.
"""
import argparse
import datetime as dt
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REFUSAL = "I don't know. That isn't in the manuals I have."
MACHINES = "the ArcLine 215 welder, the AirLine C60 compressor, the LiftLine EPT-45 pallet truck or the HygienLine CIP-400 CIP skid"
CLARIFY_MACHINE = f"Which machine do you mean: {MACHINES}?"
CLARIFY_ONE_AT_A_TIME = f"Ask about one machine at a time: {MACHINES}."
CLARIFICATIONS = {"machine": CLARIFY_MACHINE, "one_at_a_time": CLARIFY_ONE_AT_A_TIME, "model": None}
HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = {"answerable", "must_refuse", "ambiguous_equipment", "numeric", "safety_prerequisite"}
CITED = {"answerable", "numeric", "safety_prerequisite"}


def load_questions(path):
    questions = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            where = f"questions.jsonl line {line_number}"
            for key in ("id", "category", "question"):
                if not record.get(key):
                    raise SystemExit(f"{where}: missing {key}")
            category = record["category"]
            if category not in CATEGORIES:
                raise SystemExit(f"{where}: unknown category {category}")
            if category == "numeric" and not record.get("expected_value"):
                raise SystemExit(f"{where}: numeric question without expected_value")
            if category in CITED and not (record.get("expected_pdf_pages") and record.get("manual")):
                raise SystemExit(f"{where}: {record['id']} needs manual and expected_pdf_pages")
            if category not in CITED and record.get("expected_pdf_pages"):
                raise SystemExit(f"{where}: {record['id']} must not expect pages")
            if category == "must_refuse" and not record.get("manual"):
                raise SystemExit(f"{where}: {record['id']} must name the manual the question is routed to")
            if category == "ambiguous_equipment":
                kind = record.get("expected_clarification", "machine")
                if kind not in CLARIFICATIONS:
                    raise SystemExit(f"{where}: unknown expected_clarification {kind}")
                if kind == "model" and not (record.get("manual") and record.get("must_include")):
                    raise SystemExit(f"{where}: {record['id']} model clarification needs manual and must_include")
            questions.append(record)
    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        raise SystemExit("questions.jsonl: duplicate ids")
    return questions


def load_manuals(path):
    with open(path, encoding="utf-8") as handle:
        return {m["id"]: m for m in json.load(handle)["manuals"]}


def normalise_response(data):
    """Return (answer_text, citations, refused, complete) from either response shape."""
    if "segments" in data:
        answer = "".join(s.get("text", "") for s in data["segments"]).strip()
        citations = []
        for segment in data["segments"]:
            for c in segment.get("citations", []) or []:
                citations.append({
                    "document": c.get("documentTitle", ""),
                    "start_page": c.get("startPage"),
                    "end_page": c.get("endPage"),
                    "cited_text": c.get("citedText", ""),
                })
        complete = data.get("stopReason", "end_turn") == "end_turn"
    else:
        answer = (data.get("answer") or "").strip()
        citations = [{
            "document": c.get("document", ""),
            "start_page": c.get("start_page"),
            "end_page": c.get("end_page"),
            "cited_text": c.get("cited_text", ""),
        } for c in data.get("citations", []) or []]
        complete = True
    refused = data.get("refused") if "refused" in data else (answer == REFUSAL)
    return answer, citations, bool(refused), complete


def pages_cited(citations):
    pages = set()
    for c in citations:
        start, end = c.get("start_page"), c.get("end_page")
        if isinstance(start, int):
            stop = end if isinstance(end, int) and end > start else start + 1
            pages.update(range(start, stop))
    return pages


RANGE_SEPARATORS = (" to ", " - ", "-", " \u2013 ", "\u2013")


def equivalents(value):
    """Typographic equivalents the manuals' own notation allows: ranges written with "to", a hyphen or an en dash."""
    forms = {value}
    for separator in RANGE_SEPARATORS:
        if separator in value:
            forms |= {value.replace(separator, other) for other in RANGE_SEPARATORS}
    return {f.strip() for f in forms if f.strip()}


def term_position(term, text):
    """Index of the first whole-word, case-insensitive occurrence of term in text, or -1."""
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.start() if match else -1


def value_matches(expected, answer):
    folded = answer.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return any(term_position(form, folded) >= 0 for form in equivalents(expected))


def score(question, answer, citations, refused, complete, manuals):
    failures = []
    category = question["category"]
    if not complete:
        failures.append("Incomplete response")
    if category == "must_refuse":
        if not refused:
            failures.append("Expected the exact refusal sentence")
        if citations:
            failures.append("Refusal carried citations")
        return failures
    if category == "ambiguous_equipment":
        kind = question.get("expected_clarification", "machine")
        if refused:
            failures.append("Refused instead of asking which machine")
        exact = CLARIFICATIONS[kind]
        if citations and exact is not None:
            failures.append("Clarification carried citations")
        if exact is not None:
            if answer != exact:
                failures.append(f"Expected the exact {kind.replace('_', ' ')} clarification")
            return failures
        if "?" not in answer:
            failures.append("No clarifying question")
        if len(answer) >= 250:
            failures.append("Clarification longer than 250 characters")
        for term in question.get("must_include") or []:
            if term_position(term, answer) < 0:
                failures.append(f"Clarification does not name: {term}")
        for term in question.get("must_exclude") or []:
            if term_position(term, answer) >= 0:
                failures.append(f"Clarification picked a value: {term}")
        return failures
    if refused:
        failures.append("Refused an answerable question")
        return failures
    if not citations:
        failures.append("No citations")
    expected_pages = set(question.get("expected_pdf_pages") or [])
    cited = pages_cited(citations)
    if expected_pages and not (expected_pages & cited):
        failures.append(f"Cited pages {sorted(cited)} do not include expected {sorted(expected_pages)}")
    manual = manuals.get(question.get("manual") or "")
    if manual and citations:
        wrong = {c["document"] for c in citations if manual["title"] not in (c.get("document") or "")}
        if wrong:
            failures.append(f"Citations from another manual: {sorted(wrong)}")
    for term in question.get("must_include") or []:
        if term_position(term, answer) < 0:
            failures.append(f"Missing: {term}")
    for term in question.get("must_exclude") or []:
        if term_position(term, answer) >= 0:
            failures.append(f"Present but excluded: {term}")
    if category == "numeric" and not value_matches(question["expected_value"], answer):
        failures.append(f"Expected value not found: {question['expected_value']}")
    if category == "safety_prerequisite":
        limit = steps_limit(answer, question.get("must_include") or [])
        for term in question.get("prerequisite_terms") or []:
            position = term_position(term, answer)
            if position < 0:
                failures.append(f"Missing prerequisite: {term}")
            elif limit is not None and position > limit:
                failures.append(f"Prerequisite after the steps: {term}")
    return failures


def steps_limit(answer, must_include):
    """Position a prerequisite must not come after.

    When the answer has a numbered list, a prerequisite may sit anywhere before the second step: in a
    warning above the list or in step 1, which is where the manuals themselves put "switch off" and
    "lock out". Without a numbered list, it must come before the first must_include term.
    """
    numbered = [m.start() for m in re.finditer(r"(?<![\d.])\d{1,2}\.\s", answer)]
    if len(numbered) >= 2:
        return numbered[1]
    if numbered:
        return len(answer)
    positions = [term_position(t, answer) for t in must_include]
    return min([p for p in positions if p >= 0], default=None)

def percentile(values, share):
    """Nearest-rank percentile of a list of numbers; None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int(round(share * len(ordered) + 0.5)))
    return ordered[min(rank, len(ordered)) - 1]


def page_targets(question, citations):
    """Split the cited pages into on-target (expected or acceptable for this question) and off-target."""
    allowed = set(question.get("expected_pdf_pages") or []) | set(question.get("acceptable_pdf_pages") or [])
    cited = pages_cited(citations)
    return sorted(cited & allowed), sorted(cited - allowed)


def metrics(results, questions):
    """Industry-style metrics computed from the stored answers. Rules only; no model judges anything here.

    citation_precision   on-target cited pages / cited pages, averaged per answer (Ragas: context precision)
    citation_hit_rate    answers that cite at least one expected page (the pass rule for cited categories)
    exact_value_rate     numeric answers that contain the expected value as the manual prints it
    prerequisite_first   safety answers with every prerequisite present and before the steps
    abstention_rate      unanswerable questions met with the exact refusal sentence
    false_refusal_rate   answerable questions refused
    clarification_rate   ambiguous questions met with a question and no picked value
    latency_s            p50 and p95 of the time to a complete answer
    """
    by_id = {q["id"]: q for q in questions}
    cited_rows = [r for r in results if r["category"] in CITED and by_id.get(r["id"])]
    per_answer, on_total, cited_total, hits = [], 0, 0, 0
    for r in cited_rows:
        q = by_id[r["id"]]
        on, off = page_targets(q, r["citations"])
        cited = len(on) + len(off)
        if cited:
            per_answer.append(len(on) / cited)
            on_total += len(on)
            cited_total += cited
        if set(q.get("expected_pdf_pages") or []) & pages_cited(r["citations"]):
            hits += 1
    numeric = [r for r in results if r["category"] == "numeric" and by_id.get(r["id"])]
    safety = [r for r in results if r["category"] == "safety_prerequisite"]
    refuse = [r for r in results if r["category"] == "must_refuse"]
    answerable = [r for r in results if r["category"] != "must_refuse"]
    ambiguous = [r for r in results if r["category"] == "ambiguous_equipment"]

    def rate(count, total):
        return round(count / total, 3) if total else None

    exact = sum(1 for r in numeric if value_matches(by_id[r["id"]]["expected_value"], r["answer"]))
    prereq = sum(1 for r in safety if not any(f.startswith(("Missing prerequisite", "Prerequisite after")) for f in r["failures"]))
    clarified = sum(1 for r in ambiguous if not any(f.startswith(("No clarifying", "Clarification picked", "Refused instead", "Expected the exact")) for f in r["failures"]))
    seconds = [r["seconds"] for r in results if r.get("complete") and r.get("answer")]
    return {
        "citation_precision": {"value": rate(sum(per_answer), len(per_answer)), "pages_on_target": on_total, "pages_cited": cited_total, "answers": len(per_answer)},
        "citation_hit_rate": {"value": rate(hits, len(cited_rows)), "hits": hits, "answers": len(cited_rows)},
        "exact_value_rate": {"value": rate(exact, len(numeric)), "exact": exact, "answers": len(numeric)},
        "prerequisite_first": {"value": rate(prereq, len(safety)), "first": prereq, "answers": len(safety)},
        "abstention_rate": {"value": rate(sum(1 for r in refuse if r["refused"]), len(refuse)), "refused": sum(1 for r in refuse if r["refused"]), "answers": len(refuse)},
        "false_refusal_rate": {"value": rate(sum(1 for r in answerable if r["refused"]), len(answerable)), "refused": sum(1 for r in answerable if r["refused"]), "answers": len(answerable)},
        "clarification_rate": {"value": rate(clarified, len(ambiguous)), "clarified": clarified, "answers": len(ambiguous)},
        "latency_s": {"p50": percentile(seconds, 0.5), "p95": percentile(seconds, 0.95), "answers": len(seconds)},
        "not_rule_checkable": ["faithfulness", "completeness"],
    }


METRIC_LABELS = [
    ("citation_precision", "Citation precision", "on-target cited pages over cited pages, per answer"),
    ("citation_hit_rate", "Citation hit rate", "answers citing at least one expected page"),
    ("exact_value_rate", "Exact value rate", "numeric answers with the value as printed"),
    ("prerequisite_first", "Prerequisites first", "safety answers with every prerequisite before the steps"),
    ("abstention_rate", "Abstention rate", "unanswerable questions refused with the exact sentence"),
    ("false_refusal_rate", "False refusal rate", "answerable questions refused"),
    ("clarification_rate", "Clarification rate", "ambiguous questions met with a question, no value picked"),
]


def metrics_lines(m):
    lines = ["## Metrics", "", "Rule-computed from the stored answers. Faithfulness and completeness need a judge and are not in this file.", "", "| Metric | Value | Basis |", "|---|---:|---|"]
    for key, label, basis in METRIC_LABELS:
        row = m[key]
        value = row["value"]
        shown = "n/a" if value is None else f"{value * 100:.0f}%"
        counts = {k: v for k, v in row.items() if k != "value"}
        lines.append(f"| {label} | {shown} | {basis}: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + " |")
    lat = m["latency_s"]
    if lat["p50"] is not None:
        lines.append(f"| Latency | p50 {lat['p50']:.1f} s, p95 {lat['p95']:.1f} s | {lat['answers']} complete answers |")
    return lines


def write_markdown(md_path, lines, metric_block):
    body = "\n".join(lines)
    marker = "## Metrics"
    if marker in body:
        head, _, tail = body.partition(marker)
        tail = tail.split("\n## ", 1)
        rest = ("\n## " + tail[1]) if len(tail) > 1 else ""
        body = head.rstrip("\n") + "\n\n" + "\n".join(metric_block) + "\n" + rest
    else:
        parts = body.split("\nA passing score", 1)
        body = parts[0].rstrip("\n") + "\n\n" + "\n".join(metric_block) + "\n" + ("\nA passing score" + parts[1] if len(parts) > 1 else "")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(body if body.endswith("\n") else body + "\n")


class Client:
    def __init__(self, base, password):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        if password:
            body = urllib.parse.urlencode({"password": password, "next": "/"}).encode()
            self.opener.open(self.base + "/api/login", body, timeout=30).read()
            if not list(self.jar):
                raise SystemExit("Login did not set a cookie; check EVAL_PASSWORD")

    def ask(self, question):
        request = urllib.request.Request(self.base + "/api/ask", data=json.dumps({"question": question}).encode(), headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=180) as response:
            return json.load(response)


def add_metrics(json_path, questions):
    """Recompute on/off-target pages and the metrics block for a stored run. Nothing about pass/fail changes."""
    with open(json_path, encoding="utf-8") as handle:
        summary = json.load(handle)
    by_id = {q["id"]: q for q in questions}
    for r in summary["results"]:
        q = by_id.get(r["id"])
        if q and r["category"] in CITED:
            r["pages_on_target"], r["pages_off_target"] = page_targets(q, r["citations"])
    summary["metrics"] = metrics(summary["results"], questions)
    ordered = {k: summary[k] for k in summary if k != "results"}
    ordered["results"] = summary["results"]
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(ordered, handle, indent=2, ensure_ascii=False)
    md_path = os.path.splitext(json_path)[0] + ".md"
    with open(md_path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    write_markdown(md_path, lines, metrics_lines(summary["metrics"]))
    for line in metrics_lines(summary["metrics"])[4:]:
        print(line, file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=os.environ.get("EVAL_ENDPOINT", "https://demo.aitechmagic.com"))
    parser.add_argument("--demo-commit", default=os.environ.get("EVAL_DEMO_COMMIT", ""))
    parser.add_argument("--only", default="", help="comma-separated question ids")
    parser.add_argument("--dry-run", action="store_true", help="validate the question set and print the plan without calling the endpoint")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="results file date, YYYY-MM-DD")
    parser.add_argument("--metrics-from", default="", metavar="RESULTS_JSON", help="add the metrics block to an existing results file from its stored answers; pass/fail is left as produced")
    args = parser.parse_args()

    questions = load_questions(os.path.join(HERE, "questions.jsonl"))
    manuals = load_manuals(os.path.join(HERE, "manuals.json"))
    for q in questions:
        if q.get("manual") and q["manual"] not in manuals:
            raise SystemExit(f"{q['id']}: unknown manual {q['manual']}")
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    counts = {}
    for q in questions:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    print(f"{len(questions)} questions: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), file=sys.stderr)
    if args.metrics_from:
        return add_metrics(args.metrics_from, questions)
    if args.dry_run:
        for q in questions:
            print(f"{q['id']:8} {q['category']:20} {q['question']}")
        return 0
    if not args.demo_commit:
        print("Record the demo commit under test with --demo-commit or EVAL_DEMO_COMMIT.", file=sys.stderr)
        return 2
    password = os.environ.get("EVAL_PASSWORD", "")
    client = Client(args.endpoint, password)
    results = []
    for q in questions:
        started = time.monotonic()
        record = {"id": q["id"], "category": q["category"], "manual": q.get("manual", ""), "question": q["question"]}
        try:
            data = client.ask(q["question"])
            answer, citations, refused, complete = normalise_response(data)
            record.update({"answer": answer, "citations": citations, "refused": refused, "complete": complete})
            record["failures"] = score(q, answer, citations, refused, complete, manuals)
            record["pages_on_target"], record["pages_off_target"] = page_targets(q, citations)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            record.update({"answer": "", "citations": [], "refused": False, "complete": False, "failures": [f"HTTP {error.code}: {detail}"]})
        except Exception as error:  # noqa: BLE001 - every outcome is recorded, never retried
            record.update({"answer": "", "citations": [], "refused": False, "complete": False, "failures": [f"Request failed: {error}"]})
        record["passed"] = not record["failures"]
        record["seconds"] = round(time.monotonic() - started, 1)
        results.append(record)
        status = "PASS" if record["passed"] else "FAIL"
        print(f"{status} {q['id']:8} {record['seconds']:5.1f}s " + ("" if record["passed"] else "; ".join(record["failures"])), flush=True)

    passed = sum(1 for r in results if r["passed"])
    summary = {
        "date": args.date,
        "endpoint": args.endpoint,
        "demo_commit": args.demo_commit,
        "questions": len(results),
        "passed": passed,
        "by_category": {c: {"passed": sum(1 for r in results if r["category"] == c and r["passed"]), "total": sum(1 for r in results if r["category"] == c)} for c in sorted(counts)},
        "metrics": metrics(results, questions),
        "results": results,
    }
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json_path = os.path.join(HERE, "results", f"{args.date}.json")
    md_path = os.path.join(HERE, "results", f"{args.date}.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    lines = [
        f"# Results, {args.date}",
        "",
        f"{passed} of {len(results)} passed on {args.date}.",
        "",
        f"Endpoint: {args.endpoint}. Demo commit: `{args.demo_commit}`.",
        "",
        "| Category | Passed | Total |",
        "|---|---:|---:|",
    ]
    for category, c in summary["by_category"].items():
        lines.append(f"| {category} | {c['passed']} | {c['total']} |")
    failures = [r for r in results if not r["passed"]]
    lines += ["", f"## Failures ({len(failures)})", ""]
    if not failures:
        lines.append("None.")
    for r in failures:
        lines.append(f"- `{r['id']}` ({r['category']}): " + "; ".join(r["failures"]))
    lines += ["", "A passing score measures citation, refusal, numeric fidelity and clarification on these four manuals only. It does not certify answers as safe or complete and is not a release criterion for any plant. Consult the original manual and qualified personnel before operating equipment.", ""]
    write_markdown(md_path, lines, metrics_lines(summary["metrics"]))
    print(f"\n{passed} of {len(results)} passed. Wrote {json_path} and {md_path}", file=sys.stderr)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

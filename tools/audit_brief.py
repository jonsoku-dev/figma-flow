#!/usr/bin/env python3
"""Conservative local Korean/English brief checks; no API or language model.

Usage: audit_brief.py FILE [FILE ...] [--review REVIEW.json]. JSON stdout; exits 0 checked scope,
1 incompatible active requirements, 2 human review or invalid input.
A pass covers only extracted rules. Unrecognized prose remains visible for review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


RETRY = r"다시\s*연습|재시도|다시\s*풀|오답|틀리|retry|incorrect|wrong\s+answer"
RELOAD = r"새로\s*고침|리로드|reload|refresh"
HISTORICAL = r"histor(?:y|ical)|archive|as-generated|deprecated|superseded|old\s+(?:rule|version)|이전\s*(?:규칙|버전|명세)|과거|폐기|변경\s*전|(?:before|old|기존|이전)\s*(?:[:：]|$)"
EXAMPLE = r"^(?:예시|예제|example|e\.g\.)\s*[:：]"
LAST = r"남은\s*카드가?\s*(?:한\s*장|1\s*장)|마지막\s*(?:남은\s*)?카드|(?:only\s+)?one\s+(?:pending\s+|remaining\s+)?card\s+(?:remains|is\s+left)|last\s+remaining\s+card"
LIMITATION = "Pattern checks only, not complete NLP or semantic acceptance. A pass is limited to extracted facts; unrecognized rules need human review. Reviewer candidates verify current source locations only; their shared topic, scope, condition and conflict judgment remain reviewer declarations."


def has(pattern, text):
    return re.search(pattern, text, re.I) is not None


def scope_of(text, heading):
    named_deck = re.search(r"(?:deck|덱)\s+([A-Z][A-Za-z0-9_-]*)\b", text + " " + heading)
    if named_deck:
        return "deck:" + named_deck[1]
    explicit = re.search(r"\b(admin|guest|member|practice|exam|desktop|mobile)\b|관리자|게스트|회원|연습\s*모드|시험\s*모드|모바일|데스크톱", text, re.I)
    if not explicit:
        explicit = re.search(r"\b(admin|guest|member|practice|exam|desktop|mobile)\b|관리자|게스트|회원|연습\s*모드|시험\s*모드|모바일|데스크톱", heading, re.I)
    value = explicit.group(0).lower().replace(" ", "") if explicit else "default"
    return {"연습모드": "practice", "시험모드": "exam", "관리자": "admin", "회원": "member", "게스트": "guest", "모바일": "mobile", "데스크톱": "desktop"}.get(value, value)


def unresolved_condition(text):
    clean = re.sub(r"[*_`‘’“”\"']", "", text)
    if has(r"\bunless\b|아니면|제외하면", clean):
        return True
    clean = re.sub(r"로그인하면(?=\s*안)", "로그인 금지", clean)
    # A known event elsewhere in a clause cannot resolve an additional qualifier.
    korean_conditions = re.finditer(r"([^,.;]*?(?:하면|이면|라면|경우|때))(?!\s*안)(?:[,\s]|$)", clean)
    known_condition = (r"(?:" + LAST + r")(?:이면|인\s*경우|일\s*때)$|"
                       r"(?:" + RETRY + r"|" + RELOAD + r")(?:을|를)?\s*(?:선택|클릭)?(?:하면|이면|일\s*경우|할\s*때)$|"
                       r"정답을?\s*본\s*(?:경우|때)$")
    if any(not has(known_condition, match[1]) for match in korean_conditions):
        return True
    conditional = re.search(r"\b(?:if|when|unless)\s+([^,.;]+?)(?:,|\s+then\b|$)", clean, re.I)
    if not conditional:
        conditional = re.search(r"(.{1,120}?(?:하면|이면|라면|경우|때))(?:[,\s]|$)", clean)
    return bool(conditional and not has(LAST + "|" + RETRY + "|" + RELOAD + r"|정답을\s*본|answer", conditional[1]))


def fact(rule, subject, value, quote, file, line, scope, condition="default", **extra):
    return {"rule": rule, "subject": subject, "scope": scope, "condition": condition,
            "value": value, "quote": quote, "file": file, "line": line, **extra}


def extract(quote, context, file, line, scope):
    clean = re.sub(r"[*_`‘’“”\"']", "", quote)
    facts = []
    retry = has(RETRY, context)
    last = has(LAST, clean)
    # A fallback for the sole remaining card is compatible with next-pending selection.
    condition = "last-remaining-card" if last else "retry-after-answer"
    if not last and has(r"오답|틀리|incorrect|wrong\s+answer", clean):
        condition = "incorrect-answer"
    elif not last and has(r"정답을?\s*맞|정답인|(?<!in)correct\s+answer|answer\s+is\s+correct", clean):
        condition = "correct-answer"
    if retry:
        same = has(r"같은\s*(?:카드|질문)|동일한?\s*카드|현재\s*카드의?\s*질문|(?:the\s+)?same\s+card", clean)
        next_card = has(r"다음\s*(?:미완료\s*|대기\s*)?카드|next\s+(?:(?:pending|unfinished|incomplete)\s+)?card", clean)
        if same != next_card:
            if has(r"정답\s*공개\s*전|정답을?\s*보기\s*전|before\s+(?:revealing|the)\s+answer|outside\s+review|목록에서", clean):
                condition = "before-answer-or-outside-review"
            negative = has(r"(?:same\s+card|next\s+(?:pending\s+)?card).{0,15}(?:must\s+not|is\s+not)|(?:(?:do|does|must|should)\s+not|never|cannot).{0,40}(?:same|next)\s+card|(?:같은|다음).{0,25}(?:않|안\s*된|금지)", clean)
            if not negative:
                facts.append(fact("retry-target", "card", "same-card" if same else "next-card", quote, file, line, scope, condition))
    if has(RELOAD, clean):
        subject = next((name for pattern, name in [(r"점수|score", "score"), (r"검색|search", "search"), (r"진행|progress", "progress"), (r"세션|session", "session")] if has(pattern, clean)), None)
        keep = has(r"유지|보존|지속|persist|preserv|retain|keep|kept|survive", clean)
        reset = has(r"초기화|리셋|지워|사라|reset|clear|discard|lose|lost", clean)
        reset_negated = (r"(?:does?\s+not|must\s+not|never).{0,12}(?:reset|clear)|"
                         r"(?:\b(?:is|are|was|were|should|will|does?|must|can)\s*(?:not\b|n't)|\bcannot|\bnever)\s+(?:be\s+|get\s+)?(?:reset|clear(?:ed)?|lost|discarded|wiped)|"
                         r"초기화(?:하지\s*않|하지\s*말|하면\s*안|해서는\s*안)|초기화되(?:지\s*않|면\s*안)|(?:지워|사라)지(?:지\s*않|면\s*안)|잃지\s*않")
        keep_negated = r"(?:does?\s+not|must\s+not|never).{0,12}(?:persist|preserve|retain|keep)|(?:유지|보존)(?:되지\s*않|하지\s*않|하지\s*말|하면\s*안|해서는\s*안)"
        if has(reset_negated, clean):
            keep, reset = True, False
        elif has(keep_negated, clean):
            keep, reset = False, True
        elif has(r"\bnot\b|\bnever\b|n't|않|안\s|말고|금지", clean):
            keep = reset = False  # Conservative: an unrecognized negation is never guessed into a fact.
        if subject and keep != reset:
            facts.append(fact("reload-state", subject, "preserve" if keep else "reset", quote, file, line, scope, "reload"))
    if has(r"카드|cards?", clean) and has(r"덱|deck|페이지|page", clean):
        container = "page" if has(r"페이지|page", clean) else "deck"
        setting = re.search(r"(?:card\s+(?:limit|cap)|카드\s*(?:수\s*)?(?:한도|제한))\s*(?:is|=|:|는|은)?\s*(?:exactly\s*|정확히\s*)?(\d+)", clean, re.I)
        match = re.search(r"(?:(at\s+most|at\s+least|exactly|maximum(?:\s+of)?|minimum(?:\s+of)?|max\.?|min\.?|최대|최소|정확히)\s*)(\d+)\s*(?:cards?|장|개)?", clean, re.I)
        if setting:
            facts.append(fact("numeric-setting", f"{container}-card-limit", int(setting[1]), quote, file, line, scope, "configured-value", unit="cards"))
        elif match:
            kind = "min" if has(r"least|minimum|min\.?|최소", match[1]) else "exact" if has(r"exactly|정확히", match[1]) else "max"
            facts.append(fact("numeric-limit", f"cards-per-{container}", int(match[2]), quote, file, line, scope, kind, unit="cards"))
    if has(r"로그인|log\s*in|sign\s*in", clean):
        required = has(r"must\s+(?:log|sign)\s*in|로그인(?:해야|하여야)|로그인이?\s*필수", clean)
        forbidden = has(r"must\s+not\s+(?:log|sign)\s*in|로그인(?:하면\s*안|을?\s*금지)", clean)
        if required != forbidden:
            facts.append(fact("modality", "login", "required" if required else "forbidden", quote, file, line, scope))
    return facts


def incompatible(a, b):
    if (a["rule"], a["subject"], a["scope"]) != (b["rule"], b["subject"], b["scope"]):
        return False
    if a["rule"] != "numeric-limit":
        return a["condition"] == b["condition"] and a["value"] != b["value"]
    if a["condition"] == b["condition"]:
        return a["condition"] == "exact" and a["value"] != b["value"]
    bounds = {a["condition"]: a["value"], b["condition"]: b["value"]}
    return ("min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]
            or "exact" in bounds and (bounds.get("min", bounds["exact"]) > bounds["exact"] or bounds.get("max", bounds["exact"]) < bounds["exact"]))


def import_review(review, documents, aliases, active_locations):
    """Verify closed-schema candidate data against already read sources, never commands."""
    review_file = None
    if isinstance(review, (str, Path)):
        path = Path(review).resolve(strict=True)
        if path.stat().st_size > 1_000_000:
            raise ValueError("Review JSON exceeds 1 MB")
        review_file = str(path)
        review = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(review, dict) or set(review) != {"version", "reviewer", "findings"} or type(review["version"]) is not int or review["version"] != 1:
        raise ValueError("Review must have exactly version=1, reviewer, findings")

    def text_value(value, field):
        if not isinstance(value, str) or not 3 <= len(value.strip()) <= 4000 or any(ord(c) < 32 for c in value):
            raise ValueError(f"Invalid review {field}")
        if has(r"ignore.{0,30}(?:instructions|rules)|system\s+prompt|reveal.{0,30}(?:secret|credential)|(?:execute|run).{0,20}(?:shell\s+command|tool\s+call)|이전.{0,15}지시.{0,10}무시|비밀.{0,15}공개", value):
            raise ValueError("Review contains instruction-like content")
        return value.strip()

    reviewer = text_value(review["reviewer"], "reviewer")
    if not isinstance(review["findings"], list) or len(review["findings"]) > 100:
        raise ValueError("Review findings must be a list of at most 100 candidates")
    candidates = []
    for candidate in review["findings"]:
        if not isinstance(candidate, dict) or set(candidate) != {"topic", "scope", "condition", "rationale", "evidence"}:
            raise ValueError("Review candidate requires exactly topic, scope, condition, rationale, evidence")
        fields = {key: text_value(candidate[key], key) for key in ("topic", "scope", "condition", "rationale")}
        if any(fields[key].lower() in {"unknown", "default", "general", "unspecified", "기타", "미정"} for key in ("topic", "scope", "condition")):
            raise ValueError("Review topic, scope and condition must be concrete")
        evidence = candidate["evidence"]
        if not isinstance(evidence, list) or len(evidence) != 2:
            raise ValueError("Review candidate requires exactly two different source snippets")
        verified = []
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"file", "line", "quote", "sha256"}:
                raise ValueError("Review evidence requires exactly file, line, quote, sha256")
            name = item["file"]
            if not isinstance(name, str) or any(ord(c) < 32 for c in name) or ".." in Path(name).parts or "://" in name or name not in aliases or aliases[name] is None:
                raise ValueError("Review locator must name an already scanned explicit document")
            file = aliases[name]
            document = documents[file]
            if type(item["line"]) is not int or not 1 <= item["line"] <= len(document["lines"]):
                raise ValueError("Review line is outside the current source")
            quote = text_value(item["quote"], "quote")
            if quote != item["quote"] or len(quote) < 8 or quote not in document["lines"][item["line"] - 1]:
                raise ValueError("Review quote does not exactly match the current source line")
            if item["sha256"] != document["sha256"]:
                raise ValueError("Review source SHA256 changed or is missing")
            if (file, item["line"]) not in active_locations:
                raise ValueError("Review evidence must be active prose, not history, examples or headings")
            verified.append({"file": file, "line": item["line"], "quote": quote, "sha256": document["sha256"]})
        if verified[0]["quote"] == verified[1]["quote"] or (verified[0]["file"], verified[0]["line"]) == (verified[1]["file"], verified[1]["line"]):
            raise ValueError("Review evidence must have different quotes and different locations")
        candidates.append({"kind": "suggested-conflict", **fields, "evidence": verified,
                           "provenance": {"type": "reviewer-reported", "reviewer": reviewer, "review_file": review_file},
                           "locator_verification": "current-source-matched", "topic_scope_condition": "reviewer-declared", "judgment": "pending"})
    return candidates


def audit(paths, review=None):
    facts, ignored, unsupported, inputs = [], [], [], []
    documents, aliases, active_locations = {}, {}, set()
    for item in paths:
        path = Path(item).resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8")
        inputs.append(str(path))
        documents[str(path)] = {"lines": text.splitlines(), "sha256": hashlib.sha256(raw_bytes).hexdigest()}
        for alias in (str(item), str(path), path.name):
            aliases[alias] = str(path) if alias not in aliases or aliases[alias] == str(path) else None
        historical_file = any(has(r"^(?:history|historical|archive|as-generated)$", part) for part in path.parts)
        heading, historical_section, example_section, paragraph = "", False, False, ""
        headings = []
        for line, raw in enumerate(text.splitlines(), 1):
            quote = raw.strip()
            if not quote:
                paragraph = ""
                continue
            if quote.startswith("#"):
                level = len(quote) - len(quote.lstrip("#"))
                while headings and headings[-1][0] >= level:
                    headings.pop()
                title = quote.lstrip("# ")
                historical_section = has(HISTORICAL, title) or bool(headings and headings[-1][2])
                example_section = has(r"^(?:예시|예제|examples?)(?:\s|$|[:：])", title) or bool(headings and headings[-1][3])
                headings.append((level, title, historical_section, example_section))
                heading = " ".join(item[1] for item in headings)
                paragraph = ""
                continue
            location = {"file": str(path), "line": line, "quote": quote}
            if historical_file or historical_section or has(r"^(?:[-*]\s*)?(?:" + HISTORICAL + ")", quote):
                ignored.append({**location, "reason": "explicit-history"})
                continue
            if example_section or has(EXAMPLE, quote):
                ignored.append({**location, "reason": "explicit-example"})
                continue
            active_locations.add((str(path), line))
            paragraph = (paragraph + " " + quote).strip()
            context = heading + " " + paragraph
            for sentence in re.split(r"(?<=[.!?。])\s+", quote):
                sentence = sentence.strip()
                if not sentence:
                    continue
                extracted = extract(sentence, context, str(path), line, scope_of(sentence, heading))
                # Unknown conditional qualifiers cannot safely be equated with a default rule.
                if extracted and unresolved_condition(sentence):
                    unsupported.append({**location, "quote": sentence, "reason": "unresolved-condition"})
                else:
                    facts.extend(extracted)
                if not extracted:
                    unsupported.append({**location, "quote": sentence, "reason": "outside-pattern-coverage"})
    findings = []
    for index, a in enumerate(facts):
        for b in facts[index + 1:]:
            if incompatible(a, b):
                findings.append({"kind": "contradiction", "provenance": "pattern-model", "judgment": "incompatible-extracted-values", "rule": a["rule"], "subject": a["subject"], "scope": a["scope"], "condition": a["condition"] if a["condition"] == b["condition"] else "incompatible-numeric-bounds", "evidence": [a, b]})
    review_findings = import_review(review, documents, aliases, active_locations) if review is not None else []
    if review is not None and any(hashlib.sha256(Path(file).read_bytes()).hexdigest() != document["sha256"] for file, document in documents.items()):
        raise ValueError("Scanned source changed during review validation")
    status = "fail" if findings else "review" if review_findings or unsupported or not facts else "pass"
    return {"version": 1, "status": status, "inputs": inputs, "findings": findings, "review_findings": review_findings, "facts": facts,
            "sources": [{"file": file, "sha256": document["sha256"]} for file, document in documents.items()],
            "coverage": {"rules": ["retry-target", "reload-state", "numeric-limit", "numeric-setting", "modality"], "extracted_facts": len(facts), "unsupported_count": len(unsupported), "ignored_count": len(ignored)},
            "unsupported": unsupported, "ignored": ignored, "limitation": LIMITATION}


def main(argv=None):
    class JsonParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)

    parser = JsonParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--review", help="Optional local reviewer candidate JSON; verifies source locations, never semantic proof")
    try:
        args = parser.parse_args(argv)
        result = audit(args.files, review=args.review)
    except (OSError, ValueError, UnicodeError) as exc:
        result = {"version": 1, "status": "error", "category": "invalid-input", "error": str(exc), "findings": [], "limitation": LIMITATION}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "fail" else 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

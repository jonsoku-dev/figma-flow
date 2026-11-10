#!/usr/bin/env python3
"""List or plan the three independent campaign forms without executing production."""
import argparse
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parents[1] / 'library/campaign-forms.json'
PATTERNS = {
    'commemorative-event': r'commemorative|anniversary|기념[·\s-]?(?:행사|이벤트|특설|형)|기념.*행사|주년|행사형|記念|周年',
    'launch-reveal': r'launch[ -]?reveal|출시[·\s-]?(?:공개|형|예고|발표)|출시.*공개|공개형|사전등록|사전예약|신작\s*공개|preregistration|pre.registration|reveal|事前登録',
    'participation-promotion': r'participation[ -]?promotion|참여[·\s-]?(?:프로모션|형|이벤트)|참여.*프로모션|프로모션형|participation|promotional|参加',
}


def load(path=DATA):
    data = json.loads(Path(path).read_text())
    if data.get('schema') != 'figma-flow-campaign-forms-v1' or {r.get('id') for r in data.get('forms', [])} != set(PATTERNS):
        raise ValueError('Expected the three versioned campaign form definitions')
    return data


def select(prompt, context=None, data=None):
    data = data or load()
    context = context or ''
    def mentions(text):
        positive, excluded = set(), set()
        for key, pattern in PATTERNS.items():
            for hit in re.finditer(pattern, text, re.I):
                before, after = text[max(0, hit.start() - 16):hit.start()], text[hit.end():hit.end() + 16]
                denied = (re.search(r'(?:not|without|exclude)\s*$', before, re.I) or
                          re.match(r'(?:형|캠페인|은|는|을|를|\s)*(?:제외|말고|없이|금지)', after))
                (excluded if denied else positive).add(key)
        return positive - excluded, excluded
    current, excluded = mentions(prompt)
    historical, _ = mentions(context)
    numbers = {int(n) for n in re.findall(r'(?<!\d)([123])(?!\d)', prompt)}
    numeric_only = re.fullmatch(r'\s*[123](?:\s*[,/+·]\s*[123])*\s*(?:모두|전부|함께|all|both)?\s*', prompt, re.I)
    explicit_type = re.search(r'(?<!\d)[123]\s*번\s*(?:유형|형태)', prompt)
    menu_answer = historical and re.match(r'^\s*[123]\s*번(?:으로|만|을|은|\s)', prompt)
    combined_answer = historical and re.search(r'^\s*[123]\s*[,/+·]\s*[123].*(?:모두|전부|all|both)', prompt, re.I)
    excluded_numbers = {int(n) for n in re.findall(r'(?<!\d)([123])\s*번(?:은|을|는|\s)*(?:제외|말고)', prompt)}
    excluded.update(row['id'] for row in data['forms'] if row['number'] in excluded_numbers)
    # Natural-language form names win; arbitrary counts and anniversary dates are never menu answers.
    if current:
        selected = current
    elif numbers and (numeric_only or explicit_type or menu_answer or combined_answer):
        selected = {row['id'] for row in data['forms'] if row['number'] in numbers - excluded_numbers}
        if excluded_numbers and not (numbers - excluded_numbers):
            selected = historical - excluded
    elif historical and (excluded or re.search(r'모두|전부|함께|계속|이대로|all|both|continue', prompt, re.I)):
        selected = historical - excluded
    else:
        selected = historical - excluded if not re.search(r'만\b|only|제외|없이', prompt, re.I) else set()
    return [dict(row, status='planned', evidence='Content/asset coverage proposal; actual production and behavior remain unverified')
            for row in data['forms'] if row['id'] in selected - excluded]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prompt')
    p.add_argument('--context')
    a = p.parse_args()
    print(json.dumps({'schema': 'figma-flow-campaign-forms-v1',
                      'forms': select(a.prompt, a.context) if a.prompt else load()['forms']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

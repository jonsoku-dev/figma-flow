"""One destination policy for new UI: local Figma Design, or explicitly local-only output."""
import re

FIGMA = r'(?:figma|피그마|フィグマ)'
# Excluding a transport, optional mode or host tool does not exclude the design file.
CAPABILITY = r'(?:mcp|dev\s*mode|dev\s*모드|개발(?:자)?\s*모드|開発モード|computer\s*use|컴퓨터\s*사용|hooks?)'
LOCAL = (r'\blocal[-\s]+html\b|\b(?:html|web)[-\s]+only\b|\bonly\s+(?:local\s+)?html\b|'
         r'로컬\s*html|html로만|html\s*(?:화면|페이지|파일|시안)?\s*만(?!들)|웹\s*(?:페이지|사이트|화면|시안)?\s*만(?!들)|html\s*(?:だけ|のみ)')
NO_FIGMA = (rf'(?:\bwithout(?:\s+using)?|\bno(?:\s+need\s+for)?|\bexclude|\bskip|\binstead\s+of|'
            rf'do\s+not\s+(?:use|create(?:\s+an?)?)|don.t\s+(?:use|create(?:\s+an?)?))\s+{FIGMA}|'
            rf'{FIGMA}\s+(?:is\s+)?not\s+needed|'
            rf'{FIGMA}\s*(?:을|를|는|은|이|가|は|を|が)?\s*(?:(?:파일|ファイル)\s*(?:을|를|은|는|이|가|は|を|が)?\s*)?'
            rf'(?:(?:생성|작업|제작|디자인)\s*)?(?:없이|제외|미사용|사용하지|쓰지|말고|なし|不要|使わ(?:ない|ず)|いらない|'
            rf'필요\s*없|안\s*써|아니라|대신|(?:로)?\s*하지\s*말|만들지\s*마)')
# "No Figma file yet ... create it in Figma" names the destination; the missing file is not an exclusion.
PLACE_IN_FIGMA = rf'\bin\s+{FIGMA}|{FIGMA}\s*(?:에서?|で|に)'


def _excluded(s):
    for match in re.finditer(NO_FIGMA, s, re.I):
        about_file = re.search(r'file|파일|ファイル', s[match.start():match.end() + 8], re.I)
        if about_file and re.search(PLACE_IN_FIGMA, s, re.I):
            continue
        return True
    return False


def requested(text):
    """Return only an explicit destination; do not treat a bare tool ban as one."""
    s = re.sub(r'figma[-\s]*flow|피그마\s*플로우', ' ', text or '', flags=re.I)
    # Keep other occurrences of Figma (including attached Korean particles) intact.
    s = re.sub(rf'{FIGMA}\s*(?:의\s*)?{CAPABILITY}', ' optional-tool ', s, flags=re.I)
    if _excluded(s):
        return 'local'
    if re.search(FIGMA, s, re.I):
        return 'figma'
    if re.search(LOCAL, s, re.I):
        return 'local'
    return None


def resolve(brief, *, explicit=None, graph_requires=False, context=None):
    """Called for UI creation only. A planned Figma review grants no authority to write."""
    if explicit not in (None, 'local', 'figma'):
        raise ValueError('Review destination must be local or figma')
    stated = requested(brief) or requested(context)
    if graph_requires and (explicit == 'local' or stated == 'local'):
        raise ValueError('Canonical graph requires Figma review; local comparison is insufficient')
    if explicit == 'local' and stated != 'local':
        raise ValueError('Local-only review requires an explicit web-only or no-Figma brief')
    if explicit and stated and explicit != stated:
        raise ValueError('Review destination conflicts with the requested scope: ' + stated)
    return explicit or stated or 'figma'

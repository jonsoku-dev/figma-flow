"""Conservative request classification; context inspection is not an aesthetic verdict."""
import re


def authoring_held(text):
    """A user hold invalidates an earlier instruction as well as blocking a new one."""
    return bool(re.search(r'\b(?:revoke|cancel|reselect|stop|pause)\b|\bhold\s+(?:off|on)\b|(?:^|[.!?\n]\s*)(?:please\s+)?wait\b|\bwait\s+(?:for\s+(?:me|my|the user)|a moment|until)\b|(?:do\s+not|don.t|never)\s+(?:proceed|continue|start)|취소|중단|다시\s*선택|(?:진행|계속|시작)(?:하)?지\s*(?:마|말)|기다려|기다리|보류|멈춰|잠깐', text, re.I))


def authoring_excluded(text):
    return bool(re.search(r'research[ -]?only|inspect[ -]?only|references?\s+only|조사만|리서치만|분석만|참고만|참조만|검토만|열람만|調査のみ|(?:do not|don.t|never)\s+(?:create|build|design|make|implement)|(?:만들|제작하|디자인하|구현하)지\s*(?:마|말)|(?:제작|생성|구현)\s*금지', text, re.I))


def authoring_requested(text):
    """A URL supplies context; only creation, reproduction or delegation grants action."""
    if authoring_held(text) or authoring_excluded(text):
        return False
    intent = re.sub(r'https?://\S+', ' ', text, flags=re.I)
    return bool(re.search(r'\b(?:create|build|redesign|implement|make|reproduce|recreate|pick|choose)\b|(?:^|[.!?\n]\s*)(?:please\s+)?design\s+|\b(?:can|could|would)\s+you\s+(?:please\s+)?design\s+|디자인해(?:줘|주세요|라|봐)|디자인하(?:자|세요)|\b(?:use|follow|match)\s+(?:(?:the|this|that|provided|attached|existing)\s+)*(?:design|screen|reference)|만들|제작|구현|유지|따라|그대로|골라|정해|알아서.{0,12}(?:해줘|진행)|作成|作って|使って', intent, re.I))


def native_excluded(text):
    from review_destination import requested
    target = r'(?:figma|피그마|フィグマ)'
    prohibited = (target + r'(?:는|은|에|에서|을|를)?\s*'
                  r'(?:(?:작업|사용|접근|진입)(?:하)?(?:지\s*(?:마|말)|면\s*안\s*(?:돼|되))|들어가(?:지\s*(?:마|말)|면\s*안\s*(?:돼|되)))|'
                  r'(?:do not|don.t|never)\s+(?:open|access|enter|work\s+(?:in|on))\s+' + target)
    text_only = (r'(?:^|[.!?\n]\s*)(?:please\s+)?text[-\s]*only\b|'
                 r'\b(?:proceed|work|respond)\s+(?:in\s+)?text\s+only\b|'
                 r'텍스트(?:로만|만으로)\s*(?:진행|작업|응답|설명|답변|해줘)|^\s*텍스트만[.!]?\s*$|'
                 r'텍스트\s*전용(?:으로)?\s*(?:진행|작업)|文字のみ')
    return requested(text) == 'local' or bool(re.search(prohibited + '|' + text_only, text, re.I))


def direction_mode(text):
    def hit(pattern):
        return re.search(pattern, text, re.I)
    if authoring_excluded(text):
        return {'mode': 'inspect-context', 'basis': 'non_authoring_request', 'request_quote': None}
    no_compare = hit(r'no\s+compar(?:e|ison|isons)|without\s+compar|do not compare|don.t compare|비교\s*(?:없이|하지\s*(?:마|않|말)|안\s*(?:해|하))|比較(?:なし|しない)')
    compare = hit(r'compare|comparison|alternatives|비교|여러\s*시안|比較|(?:[23]|two|three)\s*(?:directions|concepts|시안)|시안\s*(?:두|세|2|3)\s*(?:가지|개)|(?:두|세)\s*(?:가지|개)\s*(?:시안|방향)')
    wait = hit(r'wait\s+for\s+(?:my|the user)|내\s*(?:답|선택).*기다|선택.*기다')
    comparison_requested = compare and not no_compare
    if compare and no_compare:
        for clause in re.split(r'[,.;!\n]', text):
            positive, negative = re.search(compare.re.pattern, clause, re.I), re.search(no_compare.re.pattern, clause, re.I)
            if positive and (negative is None or positive.start() < negative.start()):
                comparison_requested = True
                compare = positive
                break
    if wait or comparison_requested:
        return {'mode': 'compare', 'basis': 'requested_comparison_or_selection', 'request_quote': (wait or compare).group()}
    if authoring_held(text):
        return {'mode': 'inspect-context', 'basis': 'non_authoring_request', 'request_quote': None}
    single = hit(r'(?:single|one)\s+(?:direction|concept|design)|(?:한\s*가지|한|하나의?|단일)\s*(?:시안|방향)|(?:시안|방향)\s*(?:하나|한\s*가지|1개)(?:만)?')
    reference = hit(r'(?:match|follow|use|reproduce)\s+(?:the\s+)?(?:provided|attached|existing)\s+(?:reference|design|design system)|(?:match|follow|use|reproduce)\s+(?:this|that)\s+(?:screen|design|reference)|(?:첨부(?:한|된)?|기존|이|그)\s*(?:레퍼런스|화면|디자인(?:\s*시스템)?).{0,20}(?:그대로|따라|유지)')
    if reference is None and hit(r'https?://\S+') and authoring_requested(text):
        reference = hit(r'https?://\S+')
    # A palette alone is insufficient; require separate type, layout and palette constraints.
    constraints = all(hit(p) for p in (r'font|typeface|서체|폰트', r'layout|grid|column|레이아웃|그리드|열', r'#[0-9a-f]{6}\b|palette|팔레트'))
    if no_compare or single or reference or constraints:
        return {'mode': 'direct', 'basis': 'requested_single_direction' if no_compare or single else 'concrete_reference' if reference else 'explicit_type_layout_palette',
                'request_quote': (no_compare or single or reference).group() if no_compare or single or reference else text.strip()}
    return {'mode': 'inspect-context', 'basis': 'direction_unresolved', 'request_quote': None}

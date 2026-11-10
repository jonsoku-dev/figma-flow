# 로컬 자습: 기획서 → 그래프 → 화면 명세 → 구현 → 변경 검토

Figma 없이 도구의 실제 성공과 한계를 확인하는 실습입니다. 플러그인 루트에서 Python 3와 Node.js 18 이상을 사용합니다. 출력 경로는 아직 존재하지 않는 경로로 바꾸세요. 기존 프로젝트나 원본 예제는 수정하지 않습니다.

## 1. 한 번 실행하고 증거 읽기

```sh
python3 tools/run_local.py --out /tmp/figma-flow-study-001
```

기준 입력은 [번들 기획서](../../../examples/idea-notes/brief.md)입니다. 실행기는 예제를 새 경로에 복사하고 검사 결과를 저장합니다. 출력 루트의 `run.json`, `ssot-check.json`, `manifest-001.json`, `rendered/screen-graph.md`와 `trace.html`을 읽으세요. `trace.html`은 오프라인 관계 탐색용이며 검사를 실행하지 않습니다. 화면 명세는 `screen-spec.md`, 구현은 `app/`, 테스트는 `tests/`에 있습니다.

기대 결과:

- runner 종료 코드 `0`, 실제 실행한 검사와 명령이 `run.json`에 남음.
- 그래프 `validate --strict-local` 성공: 모든 선언된 요구사항이 화면/수용 기준에 연결되고 구현/검증 노드의 선언 상태를 만족함.
- Node 테스트 성공: 테스트 대역에서 확인한 동작에 한정됨.
- `ssot-check.json`의 로컬 범위가 현재이며 종료 코드 `0`: 등록된 파일의 내용이 스냅샷과 같음.

실패하면 같은 출력 경로를 재사용하지 말고 저장된 결과에서 원인을 확인하세요. 테스트 통과가 실제 IndexedDB·레이아웃·브라우저 입력의 검증을 뜻하지는 않습니다. runner는 번들 `evidence/browser.json`의 과거 관찰과 앱 해시의 일치도 검사하지만 브라우저를 새로 실행하지 않습니다. 현재 브라우저 증거는 다음 단계에서 별도로 남깁니다.

화면 명세의 화면 ID를 그래프에서 찾고 요구사항 → 화면 → 코드, 요구사항 → 수용 기준 → 테스트 경로를 각각 따라가세요. 실제 기획서의 각 검수 기준이 이 경로와 일치하는지 직접 대조해야 합니다.

## 2. 실제 브라우저에서 확인하기

출력 폴더에서 `python3 -m http.server 8765 --bind 127.0.0.1 --directory app`로 로컬 서버를 열고 승인된 브라우저 도구로 해당 주소를 확인합니다. 이미 사용 중인 포트는 바꾸세요. 빈 목록, 공백 제목 오류/포커스, 유효한 저장, 새로고침 유지, 제목·내용 검색/결과 없음, 취소를 확인합니다. 데스크톱·좁은 폭과 키보드도 검사하고 콘솔 오류와 결과를 별도 파일에 남깁니다. 다중 탭과 저장 실패는 실제로 확인한 경우만 검증으로 기록합니다. 브라우저의 origin별 저장소이므로 기존 사용자의 데이터를 지우지 않고 새 실습 origin을 사용합니다.

## 3. 의도한 변경으로 stale 만들고 살펴보기

먼저 실습용 첫 매니페스트에 대응하는 그래프를 보존하고, 변경 전 검사 결과를 만듭니다. 아직 그래프를 수정하지 않은 1단계 직후 실행하세요.

```sh
python3 - <<'PY_SAVE'
import shutil
shutil.copyfile('/tmp/figma-flow-study-001/graph.json', '/tmp/figma-flow-study-001/baseline-graph.json')
PY_SAVE
python3 tools/check_project.py /tmp/figma-flow-study-001/manifest-001.json --previous-graph /tmp/figma-flow-study-001/baseline-graph.json --intent inspect --out /tmp/figma-flow-before
```

변경 전 종료 코드는 `0`입니다. 이제 **동작 변경이 없는 문구 보완**을 출력 복사본에만 넣습니다. 파일 해시 변경은 stale을 만들지만 제품 동작의 변경을 자동 판정하지는 않습니다.

```sh
python3 - <<'PY_EDIT'
import json
from pathlib import Path
p = Path('/tmp/figma-flow-study-001/graph.json')
g = json.loads(p.read_text())
n = next(n for n in g['nodes'] if n['id'] == 'REQ-001')
n['detail'] = '실습 보완: 개인 아이디어 목록과 빈 상태를 설명한다.'
p.write_text(json.dumps(g, ensure_ascii=False, indent=2) + '\n')
PY_EDIT
python3 tools/check_project.py /tmp/figma-flow-study-001/manifest-001.json --previous-graph /tmp/figma-flow-study-001/baseline-graph.json --intent inspect --out /tmp/figma-flow-after
```

기대 결과는 종료 코드 **2**입니다. `/tmp/figma-flow-after/summary.json`에서 관계 검사는 통과하되 최신성은 달라졌는지 읽습니다. `graph-diff.html`에서 `REQ-001`의 `detail` 전후 값을 보고, `trace.html`에서 영향받은 코드·테스트를 선택해 명시된 의존 경로를 따라가세요. 실제로 선언한 경로만 표시됩니다. `check.json`의 `review_target_sha256`와 `review_affected_ids`는 다음 검토에 사용할 정확한 대상입니다. 이전 그래프를 빼면 정확한 필드 비교가 불가능하다고 표시됩니다. 잘못된 이전 그래프를 넣으면 해시 불일치로 거부됩니다. 새 snapshot만으로 stale은 해소되지 않습니다.

## 4. 실제 검토 후 재개하기

기획서/그래프의 추가 설명, 화면 명세, 구현을 대조해 동작 변경이 없는지 판단하고 테스트를 다시 실행합니다. 실습용 설명 파일에 실제 검토 결과와 실행 명령/종료 코드/검증 한계를 기록합니다. 자동 예제 문장을 검토 증거로 복사하지 마세요.

```sh
node --test --test-reporter=tap /tmp/figma-flow-study-001/tests/app.test.cjs > /tmp/figma-flow-study-001/evidence/node-tests.tap
python3 skills/figma-flow/scripts/graph.py validate /tmp/figma-flow-study-001/graph.json --strict-local
python3 skills/figma-flow/scripts/ssot.py check /tmp/figma-flow-study-001/manifest-001.json > /tmp/figma-flow-study-001/check-reviewed.json
```

테스트 결과처럼 등록된 파일을 다시 쓴 **후** 마지막 check를 실행해야 현재 상태를 고정할 수 있습니다. 실제 검토 증거를 `/tmp/figma-flow-study-001/revalidation-002.md`에 저장한 다음 다음 코드로 정확한 review 필드를 만듭니다.

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
r = Path('/tmp/figma-flow-study-001')
c = json.loads((r / 'check-reviewed.json').read_text())
assert (r / 'revalidation-002.md').is_file(), '먼저 실제 검토 증거를 작성하세요'
review = {
    'previous_manifest_sha256': json.loads((r / 'manifest-001.json').read_text())['manifest_sha256'],
    'current_state_sha256': c['review_target_sha256'],
    'affected_ids': c['review_affected_ids'],
    'evidence': 'revalidation-002.md',
    'evidence_sha256': hashlib.sha256((r / 'revalidation-002.md').read_bytes()).hexdigest(),
    'review_note': '실습 그래프 설명 보완의 동작 영향과 연결된 산출물을 검토함. 상세 범위와 결과는 evidence 참조.'
}
(r / 'review-002.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
PY
python3 skills/figma-flow/scripts/ssot.py snapshot --brief /tmp/figma-flow-study-001/brief.md --graph /tmp/figma-flow-study-001/graph.json --bindings /tmp/figma-flow-study-001/bindings.json --previous /tmp/figma-flow-study-001/manifest-001.json --review /tmp/figma-flow-study-001/review-002.json --out /tmp/figma-flow-study-001/manifest-002.json
python3 skills/figma-flow/scripts/ssot.py check /tmp/figma-flow-study-001/manifest-002.json
```

기대 결과는 검토한 상태의 새 manifest 생성과 마지막 check 종료 코드 `0`입니다. parent chain은 유지됩니다. 검토 후 파일이 달라졌으면 성공을 기대하지 말고 새 상태를 확인하고 검토하세요. review JSON 또는 증거 파일을 이후 바꾸면 `changed_review_pins`로 check가 `2`를 반환하며 그 체인을 연장할 수 없습니다. 원본 기록은 유지하고 새 검토 증거를 별도 파일로 작성합니다.

## 새 아이디어에 적용하기

runner는 번들 재현용입니다. 실제 임의 기획서는 에이전트가 [스킬의 로컬 단계](../SKILL.md#execute-a-local-run-from-any-brief)에 따라 해석하고 graph/spec/구현/증거를 작성합니다. 위 gate와 local-only snapshot/check를 실제 파일에 적용하세요. 화면 명세는 같은 의미 ID를 사용하고 bindings에는 실제 기준 원본과 증거를 등록합니다.

Figma가 요청되면 [Figma 워크플로](figma-workflow.md)를 추가하고 실제 노드·반응·재읽기 증거를 수집합니다. 로컬 실습 완료는 Figma 실사용이나 전체 제품 수용을 완료한 것이 아닙니다.

## 5. 두 프로젝트의 기능과 화면 모아 보기

먼저 검토가 끝난 첫 프로젝트의 `manifest-002.json`과 두 번째 실습 프로젝트를 준비합니다. 여기서는 같은 예제를 별도 폴더에 복사하므로 ID가 겹칩니다. 실제 프로젝트에서는 각자의 기획서·코드·증거가 연결된 매니페스트로 바꾸세요.

```sh
python3 tools/run_local.py --out /tmp/figma-flow-study-002
python3 tools/idea_catalog.py --project 개인메모 /tmp/figma-flow-study-001/manifest-002.json --project 업무메모 /tmp/figma-flow-study-002/manifest-001.json --out /tmp/figma-flow-catalog-001
```

`/tmp/figma-flow-catalog-001/index.html`을 엽니다. 검색에 `검색`을 입력하고, 프로젝트 필터를 개인메모로 바꾸고, 유형을 화면으로 바꿔 목록을 확인합니다. 필터를 해제한 다음 `REQ-001`이 서로 다른 프로젝트에 각각 남는지 확인하세요. 기능과 화면 항목의 링크로 해당 프로젝트 추적 뷰를 열 수 있습니다. `catalog.json`과 `projects/001/summary.json`, `projects/002/summary.json`에는 각 프로젝트의 결과가 따로 남습니다. 선언된 노드 상태와 등록 파일의 최신성은 서로 다른 정보입니다.

다음에는 두 번째 프로젝트의 `brief.md`에 실습 설명 한 줄을 추가한 후 **새** 출력 경로로 같은 두 매니페스트를 다시 모아 보세요. 첫 프로젝트는 현재, 둘째는 stale로 구분되어야 하며 전체 명령은 `2`를 반환합니다. 둘째를 첫 프로젝트의 성공으로 덮지 않습니다. 실제 프로젝트 테스트를 다시 실행하거나 검토를 승인하는 기능은 아닙니다.

## 내 프로젝트의 첫 기준선 만들기

기존 매니페스트가 없는 프로젝트에서 실제 기획서·그래프·바인딩과 산출물을 준비한 뒤 다음을 실행합니다. 예시 경로를 내 프로젝트로 바꾸세요.

```sh
python3 tools/check_project.py --init --brief /내프로젝트/brief.md --graph /내프로젝트/graph.json --bindings /내프로젝트/bindings.json --out /tmp/my-first-baseline
python3 tools/check_project.py /tmp/my-first-baseline/manifest-001.json --previous-graph /tmp/my-first-baseline/baseline-graph.json --intent inspect --out /tmp/my-inspection-001
```

`--init`은 strict-local 검사를 통과하는 준비된 프로젝트를 local-only로 등록합니다. `manifest-001.json`, `baseline-graph.json`, `check.json`, `summary.json`, `trace.html`을 보존합니다. 그래프의 정확한 바이트가 기준선 해시에 고정되므로 이전 그래프를 수정하거나 현재 그래프로 바꾸지 마세요. 기존 검토 체인이 있으면 4단계처럼 이어 갑니다. 기본 `--intent auto`는 frontend·design_review 프로젝트를 새 UI 생성으로 보고 현재 시안 선택(`bindings.design_directions`)을 요구합니다. 선택이 없으면 종료 코드 1(`WAIT_SELECTION`)입니다. 등록 상태를 읽기만 할 때는 `--intent inspect`를 쓰고, 실제 선택은 [시안 검토 및 사용자 선택](direction-selection.md)을 따릅니다.

## 아직 구현하지 않은 두 아이디어를 모으기

```text
$figma-flow 다음 두 아이디어를 각각 별도 그래프로 정리하고 하나의 모음으로 보여 줘.
A: 동네 도서 교환: 책을 등록하고 교환 신청을 받고 싶다.
B: 개인 운동 일지: 날짜별 운동 기록을 남기고 주간 내역을 보고 싶다.
각각 요구사항과 제안 화면을 연결하고 추정 정책은 제안으로 표시해 줘.
구현과 테스트는 만들었다고 기록하지 말고 --idea로 모음을 만들어 줘.
```

에이전트는 아이디어별 의미 ID를 가진 구조 그래프를 작성하고 원문과 제안 화면의 연결을 검토합니다. 그 뒤 다음처럼 모읍니다.

```sh
python3 tools/idea_catalog.py --idea 도서교환 /초안A/graph.json --idea 운동일지 /초안B/graph.json --out /tmp/figma-flow-drafts-001
```

유효한 초안은 종료 코드 `0`이며 화면에 `기획 초안 · 구현/증거 미검증`으로 표시됩니다. 이 성공은 모음을 만들었다는 뜻입니다. 초안에는 SSOT 검사나 구현 검증 결과가 없고 각 노드도 미검증으로 다룹니다. 구현한 프로젝트는 `--project`, 초안은 `--idea`로 섞어서 모을 수 있습니다. 실제 구현을 요청할 때는 앞의 새 아이디어 적용 절차를 진행해 명세·코드·증거를 준비한 후 첫 기준선을 만드세요.

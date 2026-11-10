# 초안에서 로컬 앱 만들기와 변경 테스트

[기존 자습 실습](live-example.md)은 번들 재현·프로젝트 등록·검토 체인을 다룹니다. 여기서는 카탈로그에서 선택한 초안 하나를 새 앱으로 만들고 변경 후 관련 테스트를 다시 실행합니다. [그래프·SSOT 계약](graph-contract.md)과 [실행 기록](run-record.md)의 증거 구분은 그대로 적용합니다. 명령은 플러그인 루트에서 실행하며 출력 경로는 매번 아직 없는 폴더로 정합니다.

## 1. 실제 복습 카드 초안 선택

이 작업공간의 입력은 다음과 같습니다. 플러그인 배포본에 이 외부 작업 폴더가 포함된다는 뜻은 아닙니다.

- 카탈로그: `../figma-flow-local-0.4.0/final/ideas/catalog.json`, 라벨 `복습 카드`.
- 원문: `../figma-flow-local-0.4.0/drafts/cards.md`.
- 초안 그래프: `../figma-flow-local-0.4.0/drafts/cards-graph.json`.

원문은 목록·질문·정답·다시 연습·완료·제목 검색을 설명하며 **“이번에는 화면 기획 초안까지만 만든다”**고 적혀 있습니다. 원문 자체는 구현 허가가 아닙니다. 현재 사용자가 선택한 초안을 앱으로 만들라고 별도 요청한 경우 그 요청을 실행 기록에 남기고 진행합니다. 원문 바이트와 초안 ID는 보존합니다. 다시 연습의 구체적인 저장 정책, 예시 카드 데이터 등 원문에 없는 결정은 제안/추론으로 기록하고 제품 의미를 바꾸는 미정 사항은 의존 작업만 차단합니다.

화면 범위는 선택한 그래프의 `SCR-CARDS-LIST`, `SCR-CARDS-REVIEW`입니다. 다른 카탈로그 항목이나 새 화면을 조용히 추가하지 않습니다. 기존 구현의 변경 요청이라면 먼저 사용자가 고른 프로젝트와 그 검토 체인을 확인합니다. 인접 폴더나 가장 최근 파일을 기존 구현 또는 승인 기준선으로 추측하지 않습니다.

## 2. 작업대에서 클릭해 생성

```sh
python3 tools/serve_ideas.py --catalog ../figma-flow-local-0.4.0/final/ideas/catalog.json --idea '복습 카드' --graph ../figma-flow-local-0.4.0/drafts/cards-graph.json --brief ../figma-flow-local-0.4.0/drafts/cards.md --selection /tmp/cards-review/selection.json --out /tmp/figma-flow-cards-build-001
```

`--selection`은 실제 사용자가 고른 시안의 선택 기록입니다([시안 검토 및 사용자 선택](direction-selection.md)). 없거나 브리프·그래프가 다르면 **앱 만들기**는 `409 WAIT_SELECTION`으로 멈춥니다. 표시된 `http://127.0.0.1:포트/`를 열고 선택한 초안의 **앱 만들기**를 누릅니다. 이 서버는 정적 카탈로그와 달리 로컬 Codex·테스트 실행을 시작하는 작업대입니다. 한 번의 서버 실행에서 지정한 출력 하나만 생성합니다. 초기 상태, 생성 중, 성공 또는 실패를 화면에서 확인하고 실제 결과는 출력 폴더의 상태·로그·검사 보고서로 확인합니다. 입력이 시작 후 바뀌거나 출력이 이미 있으면 새 이름으로 상태를 숨기지 말고 원인을 확인합니다. 단순 열람에는 `idea_catalog.py`가 만든 정적 `index.html`을 사용합니다.

## 3. 같은 작업을 CLI로 준비·생성·마무리

`promote_idea.py`는 `--catalog`, `--idea`, `--graph`, `--brief`, `--out`을 받습니다. `--catalog-sha256`, `--graph-sha256`, `--brief-sha256`으로 사용자가 검토한 정확한 바이트를 고정할 수 있습니다. 다음 예는 직접 현재 파일을 읽어 해시를 계산하므로 임의의 해시나 성공 결과를 복사하지 않습니다.

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib
import subprocess
import sys

paths = {
    'catalog': Path('../figma-flow-local-0.4.0/final/ideas/catalog.json'),
    'graph': Path('../figma-flow-local-0.4.0/drafts/cards-graph.json'),
    'brief': Path('../figma-flow-local-0.4.0/drafts/cards.md'),
}
argv = [sys.executable, 'tools/promote_idea.py', '--idea', '복습 카드',
        '--out', '/tmp/figma-flow-cards-prepared-001', '--prepare-only']
for key, path in paths.items():
    argv += ['--' + key, str(path), '--' + key + '-sha256',
             hashlib.sha256(path.read_bytes()).hexdigest()]
subprocess.run(argv, check=True)
PY
```

`--prepare-only`는 선택한 원문·초안·카탈로그 사본과 요청·프롬프트를 남깁니다. 앱과 테스트가 통과했다는 뜻은 아닙니다. 현재 세션의 에이전트가 이 새 출력 폴더의 `promotion-prompt.md`와 고정 요청을 읽고 허용된 앱·명세·그래프·바인딩·테스트를 완성한 뒤 다음을 실행합니다.

```sh
python3 tools/promote_idea.py --finish --out /tmp/figma-flow-cards-prepared-001 --selection /tmp/cards-review/selection.json
```

처음부터 자동 생성하려면 같은 입력 명령에서 `--prepare-only`를 뺍니다. 이 경로에는 인증된 Codex CLI가 필요합니다. `--finish`는 원래 고정 요청을 사용하므로 `--out`과 `--selection`만 받습니다. 자동 생성 경로에도 `--selection`이 필요합니다. `--intent technical`(준비 단계에서 지정)은 UI가 없는 기술 작업에만 씁니다. 부분 실패는 기존 출력과 로그를 확인해 해결하며 출력 폴더를 재사용한 새 생성으로 덮어쓰지 않습니다.

## 4. 자동 수행할 명세·증거 절차

에이전트는 준비된 프로젝트에서 다음 순서로 실제 산출물을 만듭니다. 스크립트의 관계·해시 검사는 이 의미 검토를 대체하지 않습니다.

1. 원문 문장과 초안 ID를 대조하여 `screen-spec.md`에 각 화면·상태·행동·수용 기준을 연결합니다. 독립 규칙은 별도 `specs/` 명세 파일로 분리하고 그래프/바인딩에서 실제 파일을 참조합니다. 해당 규칙의 requirement source도 그 명세를 사용해 공통 원문 파일의 무관한 수정과 구분할 수 있습니다. 예를 들어 승인된 다시 연습 정책을 `specs/retry.md`에 적고 `ACT-CARDS-RETRY` 및 관련 요구사항·수용 기준과 연결합니다. 새 요구사항 ID가 필요하면 근거와 승인 범위를 기록하고 기존 ID·타입·연결은 보존합니다.
2. 실제 앱의 규칙 모듈을 코드 노드와 연결합니다. `authorities.intent`는 보존한 `brief.md`, `authorities.implementation`은 **실제로 조사한 `app/` 파일**을 가리킵니다. 구현 파일을 아직 만들거나 읽지 않았다면 권위를 추측해 등록하지 않습니다. 공통 구현 권위 파일 변경은 모든 노드를 보수적으로 영향 대상으로 만들 수 있으므로 규칙별 경로는 별도 코드 증거와 `depends-on`으로 표현합니다.
3. 실제 행동을 검사하는 `tests/*.test.cjs`를 작성합니다. `test-mapping.json`에 모든 그래프 테스트 ID와 실제 테스트 파일을 대응시키고 각 파일을 해당 테스트 노드의 로컬 증거에도 등록합니다. 규칙별 명세 → 구현 → 테스트의 전파는 허용된 의존 관계로 표현하고, 의미 관계와 버전 의존 관계를 구분합니다. 예: 요구사항 → 코드 → 테스트의 `depends-on`.
4. 테스트 소스와 실행 결과를 별개 증거로 보존합니다. 자동 마무리가 남긴 `evidence/promotion-receipts/`의 파일별 TAP과 실행 영수증·`logs/`를 읽고 실제 검사와 한계를 확인합니다. `logs/tests.json`은 실제 파일별 실행과 격리 결과를, `logs/acceptance.json`은 통과한 입력·산출물 해시와 영수증 참조를 남깁니다. TAP 파일명은 테스트 파일의 정확한 프로젝트 상대 경로 UTF-8 바이트를 SHA-256한 값의 앞 16자리와 `.tap`입니다. 테스트 노드의 `source`는 해당 TAP을, 증거는 자기 매핑 파일·해당 TAP을 가리키며 수용 기준도 관련 파일 증거만 연결합니다. 변경 테스트의 파일별 TAP·표준 오류·해시·실행 명령·종료 코드는 아래 `affected_tests.py --run`의 영수증에 남깁니다. 테스트용 DOM 대역의 통과는 브라우저·키보드·레이아웃 증명이 아닙니다.
5. 등록된 파일별 증거, strict-local 관계 검사와 local-only 현재성 보고서를 읽고 상태를 기록합니다. 초안은 `planned`/`unverified`, 준비만 되면 `prepared`, 실패하면 실패 사유를 남깁니다. `accepted`는 실제 로컬 테스트 및 내용/관계 입장 검사를 통과한 범위입니다. 미실행 검사는 미실행으로 남기며 `unknown`이나 임의의 통과 문구를 증거로 삼지 않습니다. Figma는 `not_requested`입니다.

프로젝트 테스트는 읽기 전용 Codex 실행 격리와 Node 권한 모델에서 수행하며 프로젝트 밖 읽기·파일 쓰기·네트워크·자식 프로세스·worker는 허용하지 않습니다. 파일 입출력은 메모리 대역으로 검사합니다. 실행 전 격리 탐침을 통과해야 하며 격리와 실행 제한이 지원되지 않으면 해당 실행은 차단 사유로 보고합니다. 격리 없이 다시 실행하는 자동 대체는 없습니다. 브라우저 및 Figma 검증은 각각 별도 수행과 증거가 있어야 합니다.

## 5. 기존 기준선에서 영향 계획과 실제 테스트

사용자가 선택한 프로젝트의 **현재 검토 체인의 기준선**을 지정합니다. 신규 자동 생성의 첫 기준선은 생성 결과의 `admission/manifest-001.json`입니다. 기존 카드 작업을 선택했다면 실제 경로 예는 `../figma-flow-cards-work/review-cards/baseline/manifest-001.json`이며, 이를 선택했다는 이유만으로 현재/승인 상태라고 단정하지 않습니다. 먼저 `check_project.py`로 검사하고 기존 체인이 더 이어졌는지 확인합니다. 새 `--init`으로 stale 이력을 지우지 않습니다.

```sh
python3 tools/check_project.py /tmp/figma-flow-cards-prepared-001/admission/manifest-001.json --previous-graph /tmp/figma-flow-cards-prepared-001/admission/baseline-graph.json --out /tmp/figma-flow-cards-inspect-001
python3 tools/affected_tests.py /tmp/figma-flow-cards-prepared-001/admission/manifest-001.json --project /tmp/figma-flow-cards-prepared-001 --mapping /tmp/figma-flow-cards-prepared-001/test-mapping.json --out /tmp/figma-flow-cards-plan-001
python3 tools/affected_tests.py /tmp/figma-flow-cards-prepared-001/admission/manifest-001.json --project /tmp/figma-flow-cards-prepared-001 --mapping /tmp/figma-flow-cards-prepared-001/test-mapping.json --out /tmp/figma-flow-cards-tests-001 --run
```

위 명령은 절차 예이며 실행 성공을 미리 주장하지 않습니다. 매핑 파일이 없다면 4단계의 실제 그래프·테스트 파일을 조사해 먼저 작성합니다. 형태는 다음과 같고 테스트 ID는 실제 그래프와 정확히 같아야 합니다.

```json
{
  "version": 1,
  "tests": {
    "TEST-CARDS-FLOW": ["tests/flow.test.cjs"],
    "TEST-CARDS-RETRY": ["tests/retry.test.cjs"]
  },
  "inputs": ["tests/harness.cjs"]
}
```

이 ID/파일 조합은 기존 카드 작업의 예입니다. 새로 생성된 앱이 같은 테스트 ID나 파일을 쓴다고 가정하지 않습니다. `inputs`에는 테스트가 읽는 공통 모듈 등 추가 고정 파일을 실제 경로로 등록합니다. 선언되지 않은 import는 드리프트 검사 범위 밖입니다.

계획만 실행하면 `plan.json`을 남기며 테스트는 실행하지 않습니다. `scope`, `fallback`, `global_change`, 영향 사유/경로, `selected_tests`, 제외 목록과 실제 선택 파일을 확인합니다. 변경 경로의 어느 가지라도 테스트까지 이어지지 않거나 전체 테스트 경로가 충분하지 않으면 전체 매핑으로 넓힙니다. 공통 기준 원본·brief·bindings 변경과 `--all`도 전체 매핑을 선택합니다. 경로는 선언된 영향 후보이며 의미상 완전성을 보장하지 않습니다. 공유 테스트 파일 때문에 추가 실행된 ID와 부분 파일 실행 ID도 구분합니다.

`--run`은 선택한 **파일별로** Node 테스트를 실행하고 `node-tests/` 아래 파일별 TAP·표준 오류와 실행 로그, 최상위 `receipt.json`을 남깁니다. 영수증에서 실행 결과, 격리 검사, 파일별 명령·해시·종료 코드, 실행 오류, 전후 입력 해시와 `drift`를 확인합니다. `receipt_directory` 기준 상대 경로로 개별 증거를 찾습니다. 드리프트나 실패는 통과가 아닙니다. 실행 전 오류는 `error.json` 등 실제 출력과 종료 코드를 보고하고, 영수증이 없는 상태를 성공으로 해석하지 않습니다. 변경이 없어 선택 파일이 없을 때 계획은 유효할 수 있지만 새 테스트 통과를 뜻하지 않습니다.

## 6. 영수증을 고정하고 검토 체인 이어 가기

생성 수락 기록과 변경 테스트 영수증은 서로 다른 실행 범위로 보존합니다. 실제 검토 증거에 선택 기준선, 변경 ID, 규칙 명세, 실제 수정 파일, 선택/제외 이유, 파일별 결과와 영수증 경로·SHA-256, 브라우저 등 미검증 범위를 기록합니다. 필요한 새 증거를 그래프/바인딩에 연결한 **후** 마지막 `ssot.py check OLD_MANIFEST`를 저장합니다. 해당 결과의 `review_target_sha256`와 정확한 `review_affected_ids`, 원래 매니페스트의 `manifest_sha256`, 실제 검토 증거 바이트의 SHA-256으로 검토 JSON을 만듭니다.

[정확한 review JSON 계약](graph-contract.md#reviewed-resumption)과 [실행 가능한 기존 검토 예](live-example.md#4-실제-검토-후-재개하기)를 따라 `snapshot --previous OLD_MANIFEST --review REVIEW_JSON --out NEW_MANIFEST` 후 새 매니페스트를 다시 검사합니다. 체인의 매니페스트는 같은 폴더에 둡니다. 영수증과 검토 증거·review JSON은 이후 변경하지 않습니다. 바뀌면 새 상태를 다시 검토합니다. 테스트 영수증 자체는 그래프 상태를 갱신하거나 stale을 해제하거나 검토를 승인하지 않습니다.

## 검토된 앱 다시 열기

`tools/serve_ideas.py`의 원래 인수(카탈로그, 초안 이름, 그래프, 원문, 결과 경로)를 그대로 쓰고 `--open-reviewed` 뒤에 해당 프로젝트의 `admission/manifest-NNN.json`을 붙입니다. 작업대는 같은 초안에서 생성한 승인 기록, 파일 해시와 매니페스트 계보를 확인합니다. **완성된 앱 열기**는 제어 API가 없는 별도 루프백 주소입니다. 작업대를 종료하면 그 미리보기도 종료됩니다. 원문이 바뀌었거나 근거가 오래됐으면 먼저 해당 프로젝트의 변경 검토를 진행하세요.

새 초안의 복구 가능한 계약 오류나 실제 테스트 실패에는 생성기가 한 차례 수정 작업을 할 수 있습니다. 각 시도의 로그를 보존하며 검사를 통과한 테스트 영수증만 승인 경로에 기록합니다. 입력 핀 변경이나 격리 검사 실패는 부분 실패로 남습니다.

검토 후 테스트 증거 파일을 새 버전의 파일로 바인딩할 때, 양쪽 매니페스트가 같은 정책 해시를 가지고 권위·정책이 유지되면 변경한 증거의 노드와 명시된 의존 노드에 재검토를 적용합니다. 이전 형식처럼 정책의 일치를 입증할 수 없는 기준선이나 전체 기획서·권위 변경에서는 범위를 보수적으로 넓힙니다.

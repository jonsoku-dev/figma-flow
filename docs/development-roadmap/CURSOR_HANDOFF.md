# Cursor에서 한 개발 항목을 구현하기

이 전달서는 저장소 안의 작업을 시작하는 프롬프트다. 문서 자체는 설치·외부 게시·실제 Figma 파일 변경 권한이 아니다. 현재 사용자의 요청과 적용되는 `AGENTS.md`를 따른다.

## 공통 시작 프롬프트

아래 프롬프트의 `RD-01`을 이번에 구현할 ID로 바꾼다. Cursor에 저장소 루트를 연 상태에서 전달한다.

```text
이 저장소 Figma Flow의 RD-01 한 항목을 구현해줘.

먼저 AGENTS.md, docs/development-roadmap/README.md,
docs/development-roadmap/CURRENT_STATE.md를 읽어라.
README에서 해당 ID의 feature.md, design.md, tasks.md를 찾아 전부 읽어라.
문서의 제안 API·새 파일을 현재 구현된 기능으로 간주하지 마라.
현재 branch, HEAD, dirty changes, 실제 owning source와 기존 tests를 확인해라.
기준 9a6f8ba 이후 변경은 현재 코드에서 대조하고 기존 수정은 보존해라.

tasks.md의 첫 미완료 구현 단위 하나를 끝내라.
문서에 적힌 파일·모듈의 소유권을 먼저 선언하고 한 파일에 작성자를 겹치지 마라.
같은 목적의 helper·reader·queue·component가 있으면 재사용해라.
새 framework, chart dependency, LLM server, 임의 Figma JavaScript 실행기를 추가하지 마라.
명시적으로 소유한 값만 수정하고 기존 node ID·main component·사용자 override를 보존해라.
입력 pin, pairing, revision, runtime freshness, 불확실 쓰기 차단을 유지해라.

관찰 가능한 인수 조건에 실패하는 작은 재현을 먼저 고정해라.
해당 테스트·실제 생성 bundle·변경된 패널을 검증해라.
UI 변경은 실제 브라우저에서 주요 상태·폭·테마·키보드·reduced motion·console을 확인해라.
실제 Figma 쓰기는 현재 사용자 권한 안의 전용 fixture에서만 실행해라.
공식 Figma MCP나 Computer Use가 없으면 현재 prepared-task/manual JSON 경로를 사용해라.
실행할 수 없는 관찰은 미검증으로 남기고 성공 영수증을 만들어내지 마라.

마지막에 구현 diff를 읽고 불필요한 추상화·중복·무관한 변경을 제거해라.
CHANGELOG와 skills/patch-knowledge/SKILL.md에 따른 상세 Wiki를 갱신해라.
실행한 명령, 결과, 실제 관찰, 미검증 조건을 구분해 보고해라.
현재 요청에 push·배포·설치 권한이 없으면 검증한 로컬 변경으로 마무리해라.
```

## 항목 색인

[계획 표](README.md)의 RD-01부터 RD-09까지를 한 항목씩 고른다.

- [RD-01](RD-01-components/feature.md) 재사용 컴포넌트와 편집 속성
- [RD-02](RD-02-layer-structure/feature.md) 의미 있는 계층
- [RD-03](RD-03-task-dependencies/feature.md) 작업 간 의존성
- [RD-04](RD-04-selective-sync/feature.md) 동기화 변경을 골라 적용
- [RD-05](RD-05-asset-inventory/feature.md) 입력 사진·글꼴·CSS 자산 목록
- [RD-06](RD-06-native-read/feature.md) 목적별 네이티브 읽기
- [RD-07](RD-07-runtime-boundaries/feature.md) 제어 전송과 실행 정책
- [RD-08](RD-08-operation-lifecycle/feature.md) 실행 수명주기와 충돌 복구
- [RD-09](RD-09-audit-log/feature.md) 진단 기록 내보내기

## 문서에서 실행으로 옮기는 순서

1. `feature.md`의 ID별 인수 조건을 해당 변경의 checklist에 옮긴다. 새 기능 등록이 필요하면 기존 [스펙 계약](../../specs/README.md)에 맞춰 requirement·screen·action·code·test graph를 작성한다.
2. `design.md`의 기존 경로와 제안 경로를 구분한다. 현재 소스에서 심볼을 찾고 실제 변경 파일을 확정한다.
3. `tasks.md`의 단위를 순서대로 구현한다. API 기준을 바꿔야 하면 기준과 구현을 한 diff에서 함께 낮추지 않는다.
4. 이름이 적힌 기존 검사를 실행한다. 새 동작은 사용자가 관찰할 결과를 검사하며 내부 함수 호출 순서만 고정하지 않는다.
5. UI와 Figma의 결과를 코드 검사와 따로 남긴다. 로컬 원시 readback과 키는 `.figma-flow/`에 보관하며 공유 기록에는 최소 요약만 적는다.

## 빠른 검사와 최종 검사

빠른 반복에는 각 작업서의 좁은 명령을 쓴다. React 원본이 바뀌면 `npm --prefix panel-ui run build`로 생성 파일을 갱신하고 함께 검수한다. 생성 파일만 손으로 고치지 않는다. 패키지 매니페스트 버전과 테스트의 내부 fixture 버전은 구분한다.

최종 통합은 변경 범위에 맞춰 다음 기존 경로를 사용한다.

```sh
python3 -B -m unittest discover -s tests
node --test tests/*.cjs
python3 -B -m unittest discover -s examples/native-direction-review -p test_demo.py
python3 tools/patch_knowledge.py verify --ref HEAD
```

전체 검사를 이미 통과한 같은 소스에서 문서만 수정했다면 무관한 실제 Figma 쓰기를 반복하지 않는다. 테스트를 생략한 이유와 소스의 동일성을 보고한다. Git 기록 검사는 실제 커밋 뒤 수행한다. 자기 SHA 순환은 [제품·기록 발행 절차](../llm-wiki/integration.md)로 처리한다.

## 작업 결과 형식

```text
항목 / 구현 단위:
기준 HEAD / 최종 HEAD 또는 미커밋 diff:
수정한 파일:
인수 조건별 결과:
정적·자동 검사:
실제 브라우저·Figma 관찰:
보존한 데이터와 호환성:
미검증·실패·남은 위험:
CHANGELOG / 상세 Wiki:
```

실패한 외부 CLI를 반복 호출하며 기다리지 않는다. 연결·인증·쿼터·스트림 오류는 보존하고, 소유 변경을 확인한 뒤 사용 가능한 실행 경로로 작업을 이어 간다. 다른 작업자가 만든 부분 변경을 덮어쓰지 않는다.

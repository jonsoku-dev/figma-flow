# NF-03 실행 원인과 상세 차이 탐색

상태는 **PROPOSED**다. 기존 의존성 차트와 최근 이력은 유지하고 원인 탐색과 필드 차이를 추가한다.

## 기능 계약

사용자는 "이 화면이 왜 바뀌었나", "지금 실패한 실행은 어느 입력을 사용했나"를 실행·task·artifact를 오가며 확인하고 싶다. 새 결과는 실행 상세, exact artifact revision의 전후 차이, 선행/후행 근거 탐색이다. 이력 조회는 읽기 전용이고 재실행·자동 복구 권한을 만들지 않는다.

전체 이벤트를 새 저장소로 복제하거나 UI telemetry를 canonical phase로 바꾸지 않는다. 시각적으로 이어진 노드를 인과관계로 추정하지 않는다. LLM이 작성한 원인 설명을 실제 실행 사실로 저장하지 않는다.

## 현재 경로와 확장 위치

- `tools/figma_control.py`의 `record_phase`, `journal_history`, `history`, `conflict_detail`가 canonical phase와 충돌 정보를 갖는다. `history`는 exact file/page/runtime을 요구하며 최근 80개를 반환한다.
- `tools/figma_workspace.py`의 `normalize_task_dependencies`, `dependency_history`, `task_artifacts`, `task_input_freshness`가 정확한 revision/digest를 처리한다.
- `figma-bridge/workspace_host.js`의 `workspaceJournalHistory`와 `panel-ui/src/Workspace.jsx`의 History·dependency view가 이미 있다. 차트를 새로 만드는 것이 아니다.
- `panel-ui/src/dependencyView.mjs`, `figma-bridge/audit_log.js`, `panel-ui/src/DiagnosticExport.jsx`의 관계·진단·redaction 처리를 재사용한다. 진단 로그를 phase 원장으로 승격하지 않는다.

## 데이터와 인터페이스 설계

기존 `/control/history` 요청과 80개 요약을 호환 유지한다. 새 읽기 endpoint 제안은 `/control/history-detail`이며 요청은 현재 session/file/page/runtime과 `operation_id`를 모두 요구한다. 서버는 같은 scope의 canonical request가 존재하는지 확인한 뒤 아래 형태의 제한된 DTO를 만든다.

```json
{"schema":"figma-flow-operation-detail-v1","operationId":"exact-id","task":{"key":"screen-a","revision":"sha256"},"classification":"recorded","phases":[],"relations":[{"type":"declared-dependency","taskKey":"tokens","revision":"sha256","artifactSha256":"sha256"}],"diff":{"status":"unavailable","reason":"before-artifact-missing","fields":[]}}
```

관계 type은 `declared-dependency`, `recovery-of`, `artifact-input`만 허용한다. 관측된 canonical ID만 연결하고 UI execution ID와 control operation ID를 혼용하지 않는다. phase의 순서는 canonical 이벤트에서 읽는다. 시각적 시간 정렬은 원인 순서와 다를 수 있다.

차이는 동일 semantic key의 허용된 design 필드만 `{key, field, before, after}`로 반환한다. 추가·삭제·타입 변경은 별도 kind다. before/after가 exact revision으로 보존되지 않았으면 `unavailable`이다. 최신 graph와 오래된 native readback을 섞지 않는다. 충돌 상세는 예상값·관측값·범위·원인을 구분하되 현재 readback 보존 계약 이상으로 raw 내용을 노출하지 않는다.

상세 응답은 최대 256 KiB, diff는 최대 200행을 제안한다. 넘으면 `truncated: true`와 읽기 전용 범위 안내를 표시한다. 초기 버전은 전역 검색·무제한 pagination을 제외한다. 중첩 artifact 접근은 기존 private path·symlink·digest 검사를 통과해야 한다.

## 화면 설계와 상태

History 행의 **상세 보기**를 누르면 같은 패널의 상세 영역을 연다. 상단은 task/revision·기록 분류·phase와 관측 범위다. 본문은 "입력", "변경 차이", "연결된 실행" 순서다. dependency 링크는 현재 revision인지 과거 고정 revision인지 표시한다. 뒤로 가면 기존 필터·스크롤·선택 행을 복원한다.

상태는 loading, recorded, legacy, unknown, unavailable, scope-changed, error다. legacy와 unknown에는 없는 phase를 생성하지 않는다. 실패 메시지는 redacted reason code와 사용자 행동으로 표시한다. scope가 바뀌면 이전 상세를 지우고 재선택한다. 클릭이 실행이나 mutation을 일으키지 않는다.

그래프는 보조 정보이며 동일 관계를 텍스트 목록으로 제공한다. 상세 제목으로 focus를 옮기고 닫으면 호출 버튼으로 복원한다. diff 표에는 caption·열 제목을 제공하며 좁은 화면에서는 가로 스크롤이나 카드 목록으로 읽을 수 있게 한다. 색상만으로 추가·삭제·충돌을 구분하지 않는다. 전체 패널을 키보드로 탐색할 수 있어야 한다.

개인 문구·텍스트 입력·native raw readback·bearer·로컬 경로는 기본 diff에 넣지 않는다. TEXT 내용의 공유는 기본 비활성이고 길이·변경 여부만 제공한다. 상세 local export도 기존 redaction 규칙을 적용한다. 서버는 사용자 제공 파일 경로나 임의 operation ID로 다른 page의 내용을 읽지 않는다.

## 호환성과 복구

저장 journal schema는 우선 변경하지 않고 읽기 projection으로 만든다. 새 상세를 제거해도 기존 phase·history는 같다. 기존 자료에 before artifact가 없으면 unknown으로 남긴다. 새 자료를 보존해야 할 때는 source artifact의 보존 정책과 private 저장 상한을 별도 명시하고 임의로 무기한 보관하지 않는다.

## 작은 작업과 한 writer 경계

1. `tools/figma_control.py`, 새 `tests/test_operation_detail.py` 소유자가 같은 scope 조회·차이 projection과 누출 방지 검사를 만든다.
2. `figma-bridge/workspace_transport.js`, `figma-bridge/workspace_control.js`, `figma-bridge/workspace_host.js`, 새 `tests/nf03_history_detail.cjs` 소유자가 새 읽기 route와 오류 전달을 연결한다. 1번 API가 확정된 뒤 시작한다.
3. `panel-ui/src/Workspace.jsx`, `panel-ui/src/styles/workspace.css`, `figma-bridge/locales/workspace.json` 소유자가 상세·뒤로가기·텍스트 관계와 접근성 상태를 구현한다.
4. 통합 담당자가 새 artifact·legacy·scope 변경·잘린 diff를 실제 패널에서 검증하고 생성 패널 자산을 빌드한다.

## 인수와 검증

```sh
python3 -B -m unittest discover -s tests -p 'test_rd08_journal_history.py'
python3 -B -m unittest discover -s tests -p 'test_rd08_conflict_detail.py'
python3 -B -m unittest discover -s tests -p 'test_rd03_task_dependencies.py'
node --test tests/test_workspace_host.cjs tests/test_workspace_activity.cjs
npm --prefix panel-ui run build
```

새 검사 제안은 `python3 -B -m unittest discover -s tests -p 'test_operation_detail.py'`와 `node --test tests/nf03_history_detail.cjs`다. 최소 시나리오는 exact scope 404, 타 page/runtime 거절, legacy unknown, 두 revision diff, artifact 누락, recovery 관계, UI ID 오인 방지, 응답 상한, redaction이다. 실제 패널에서 History → 상세 → 선행 artifact → 뒤로가기의 focus/필터 복원과 네트워크 쓰기 부재를 확인한다. 요약 80개 제한이 유지되고 상세 조회가 파일/페이지를 전환하지 않아야 한다.

## Cursor 구현·테스트 프롬프트

```text
NF-03의 읽기 전용 실행 상세와 원인 링크만 구현하라. 현재 journal/dependency/history UI가 이미 있음을 전제로 모든 호출 경로를 읽어라. 소유 범위는 작업 1~3 파일과 필요한 패치 기록이며 한 파일은 한 writer다. 기존 dirty 변경을 보존하라. canonical ID와 exact revision/digest만 관계 근거로 사용하고 UI event·시간·LLM 설명으로 phase나 원인을 만들지 말라. before 자료가 없으면 unavailable로 남겨라. history 요약 80개와 기존 API는 유지하라. raw 텍스트·토큰·경로 누출, 임의 파일 경로, 자동 재실행, 신규 저장소, 게시·커밋은 금지한다. 새 독립 검사와 기존 명령을 실행하고 실제 패널의 keyboard/focus·scope-change·뒤로가기를 확인하라. 실제 패널을 사용할 수 없으면 해당 인수는 미검증이다. 반환은 파일, DTO·redaction 결정, 명령 결과, 관측 화면/네트워크 근거와 남은 위험이다.
```

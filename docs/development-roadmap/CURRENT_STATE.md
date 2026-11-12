# 개발 계획의 현재 구현 기준

2026-11-13 검증 스냅샷은 `main`의 `7b5ae4091641430d891e0c110c8efdb9a845a6ce` 위에 미커밋 통합 변경이 있는 0.27.0 후보다. 현재 [plugin.json](../../plugin.json)의 버전과 설치된 런타임 버전은 구분한다. Codex 설치 플러그인은 아직 0.26.3이며 실제 Figma native 런타임은 0.27 후보로 실행됐다. 후보 push·설치 후 검증은 대기이며 이 문서 갱신 자체는 새 설치나 실행의 증거가 아니다.

Cursor의 기존 구현 보고는 역사 기록이다. 현재 계약은 아래 소스와 각 RD 설계서에 맞춘다. [최종 인수 기록](FINAL_ACCEPTANCE.md)이 실제 브라우저·Figma 관찰과 미검증 범위를 관리한다. 검사 파일의 존재, 과거 통과, version 문자열만으로 인수를 완료하지 않는다.

## 현재 후보의 구현 경로

| 항목 | 실제 구현과 유지할 경계 |
| --- | --- |
| [RD-01](RD-01-components/design.md) | [code.js](../../figma-bridge/code.js)는 선언한 축의 기존 정의와 축에 배정되지 않은 default 정의를 보존한다. TEXT property의 실제 반환 key를 main과 instance에 연결한다. 미선언 variant 조합을 만들지 않는다. optional BOOLEAN·INSTANCE_SWAP 양성 생성은 미구현이며 NF-01 후속 범위다. |
| [RD-02](RD-02-layer-structure/design.md) | [direction_review.js](../../figma-bridge/direction_review.js)와 [design_directions.py](../../tools/design_directions.py)는 선언한 Frame, Group, Auto Layout과 부모 관계를 검증한다. Auto Layout 부모의 FILL을 유지하고 명시적 clipped Frame scroll을 실제 overflow getter로 대조한다. |
| [RD-03](RD-03-task-dependencies/design.md) | [figma_workspace.py](../../tools/figma_workspace.py)의 `--depends-on`은 현재 또는 trusted history의 exact artifact revision과 digest를 고정한다. [Workspace.jsx](../../panel-ui/src/Workspace.jsx)는 한 단계 SVG와 텍스트 관계 및 freshness를 표시하며 자동 실행하지 않는다. |
| [RD-04](RD-04-selective-sync/design.md) | [graph_sync.py](../../tools/graph_sync.py)의 host manifest와 [graph_token_sync.js](../../figma-bridge/graph_token_sync.js)의 protocol 2 `selected_ids`가 선택 권한을 고정한다. 공유 root group은 쪼갤 수 없고 CAS 검사는 유지한다. partial readback은 전체 pairing 완료가 아니다. |
| [RD-05](RD-05-asset-inventory/design.md) | [input_effect.py](../../tools/input_effect.py)의 v3 record를 prepare `--input-record`와 `--input-root`로 admission한다. canonical 자산과 복수 출처를 보존하고 private root, source hash, replay와 exact revision의 `inputFreshness`를 검사한다. 자산 목록은 실제 렌더 성공률이 아니다. |
| [RD-06](RD-06-native-read/design.md) | [native_semantic_read.js](../../figma-bridge/native_semantic_read.js)는 full과 제한된 summary를 같은 reader에서 실제 getter로 읽는다. 표준 discovery의 `discoverGraphSummary`는 허용된 주 페이지의 width/height만 새로 읽고 정확한 partial coverage를 표시한다. 기본 full은 허용된 모든 페이지를 읽는다. summary는 complete false이며 full 검증에 사용할 수 없고 full fallback·session snapshot cache·쓰기가 없다. |
| [RD-07](RD-07-runtime-boundaries/design.md) | [workspace_transport.js](../../figma-bridge/workspace_transport.js)는 bounded loopback 전송과 15초 deadline을 맡는다. [workspace_control.js](../../figma-bridge/workspace_control.js)는 domain 정책을 유지하고 publisher는 trusted 모듈 목록으로 조립한다. |
| [RD-08](RD-08-operation-lifecycle/design.md) | [figma_control.py](../../tools/figma_control.py)는 canonical phase journal과 exact scope의 history를 제공한다. native-started는 실행 직전 확인 경로에서만 기록하며 claim이나 UI event로 추정하지 않는다. 불확실 쓰기 차단과 관측 값은 보존한다. |
| [RD-09](RD-09-audit-log/design.md) | [DiagnosticExport.jsx](../../panel-ui/src/DiagnosticExport.jsx)는 [audit_log.js](../../figma-bridge/audit_log.js)의 redacted 기록을 읽기 전용 표시·로컬 다운로드한다. 요청이나 문서 mutation 없이 없는 사실을 unknown과 unobserved로 남긴다. |

## 사용자 문서와 네이티브 구조의 경계

Frame은 크기·배경·clip·화면 배치를 맡고, Group은 정적 시각 묶음에 한정한다. 반복 UI는 Component와 Instance를 유지하며 detach하지 않는다. Auto Layout은 선언한 행·열 관계에만 적용한다. Group을 늘리거나 모든 화면을 자동 추정하는 것이 목표가 아니다.

일반 가져오기를 같은 source로 재실행하면 기존 main·set·instance와 사용자 override를 보존한다. 선언 충돌은 진단하고, 새 구조나 속성에 맞추려고 기존 사용자 데이터를 자동 재생성하지 않는다. file/page/revision/source pin과 private artifact 검사는 UI 편의 때문에 생략하지 않는다.

원시 readback, 개인 문구, bearer·pairing 값과 설치 경로는 공유 요약에 넣지 않는다. task dependency, UI execution ID, canonical control operation ID는 다른 식별자다. 하나를 다른 실행 권한이나 복구 증거로 사용하지 않는다.

## 실제 인수와 남은 범위

[최종 인수 기록](FINAL_ACCEPTANCE.md)의 45 AC는 명시된 fixture/runtime 범위에서 통과했다. 이는 45 REQ의 모든 양성 기능이나 최종 출시 완료를 뜻하지 않는다. RD-01 optional BOOLEAN·INSTANCE_SWAP 생성은 미구현이며 [NF-01](../next-roadmap/NF-01-component-families.md)은 PROPOSED다.

현재 producer의 R8은 44개 화면·4,820개 노드·Group 2개·main 24개·set 2개·instance 494개·variable 69개를 실제 읽고 정상 상위·순수 native 검증을 통과했다. 생성 485.154초, 같은 패킷 재실행 15.502초의 기존 페이지·전체 ID 보존은 서로 다른 작업량이므로 성능 배수로 비교하지 않는다. 공개 [grouping-qa.json](../../apps/little-hands/design/grouping-qa.json)은 R7 대비 leaf 3,171개 bbox 차이 0·Frame clip 550개·reaction node 314개 보존을 기록한다.

R7 실제 opacity 0.9 override는 재실행에서 보존됐다. 숫자 1 복원 뒤 정상 검증이 통과했지만 보관된 R7에 explicit flag가 남으며 새 R8에는 opacity override가 없다. 사람의 창작 품질·production admission과 실제 앱 영속 Graph SSOT·물리 기기·공개 DNS/TLS·실제 chat 첨부는 확인하지 않았다. 전체 clean package 검사·CI·release·설치는 다음 실행이며 이 문서는 성공을 미리 선언하지 않는다. 최종 소스·실제 설치 상태는 [release Wiki 기록](../llm-wiki/README.md)이 기준이다.

기존 61개 회귀 사례, 실기기, 데스크톱 원본 첨부 UI, 실제 브라우저 200% 확대, 독립적인 Figma 원격 저장 검증, 글꼴 바이너리 동일성은 해당 범위의 현재 근거가 있어야 통과다. 과거 기록은 새 checkout의 성공 증거가 아니다. 확정된 결과만 최종 인수 기록에 연결한다.

## 표준 discovery 요약 읽기의 현재 근거

[graph_sync.py](../../tools/graph_sync.py)의 생성 host와 [GraphPanel.jsx](../../panel-ui/src/GraphPanel.jsx), [legacy 패널](../../figma-bridge/graph-panel.html), [번역](../../figma-bridge/locales/graph.json)에 별도 요약 동작이 연결됐다. `coverage.pageIds`는 주 페이지 하나이고 `fields`는 width/height다. `nodeIds`·`omitted`·`complete:false`를 표시하며 `expected_scope`의 전체 허용 범위를 실제 읽은 범위와 혼동하지 않는다. 진단은 가장 최근 읽기의 정확한 범위를 사용한다.

주 세션은 실제 R7에서 요약 4,818개 노드의 width/height가 이전 full과 일치하고 불일치가 0개임을 확인했다. 진단 JSON은 summary·complete false 및 node ID/field/omission 목록과 정확히 일치했고 무거운 필드는 없었다. 같은 summary로 일반 graph import `--apply`와 pair를 시도하면 거절됐으며 출력이 생성되지 않고 graph bytes가 보존됐다. 이후 full 읽기로 진단이 교체되는 실제 GUI 관찰도 확인했다. 추가 14개 full/summary freshness 쌍과 partial 소비자 직접 검사를 최종 인수 기록에 연결했다. cache event integration이나 모든 문서의 속도 향상을 주장하지 않는다.

[고정 회귀 검사](../../tests/finalize_discovery_summary.cjs)는 기준 커밋에서 제품 변경 전에 보존했다. 변경 전 `0 !== 2`의 예상 assertion 실패와 변경 후 같은 Git blob의 통과는 주 세션 보고다. 문서 작성자는 검사·GUI·생성기를 재실행하지 않았다. session cache 제안은 [NF-02](../next-roadmap/NF-02-incremental-native-read.md)의 PROPOSED 상태다.

R8 named saved version을 실제 Figma history에서 확인하고 공식 UI로 로컬 .fig backup을 보존했다. 이는 로컬 보존·UI 관찰이며 독립적인 원격 암호학적 저장 검증은 아니다. 스냅샷 이후의 실제 설치·release 영수증은 Wiki release 페이지에서 따로 확인한다.

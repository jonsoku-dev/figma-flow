# Codex 최종 인수 매트릭스

[최종 인계](CODEX_FINAL_HANDOFF.md)의 미검증 범위를 구현·자동 검사·브라우저·Figma로 구분한다. 인계의 과거 버전·푸시 제한을 현재 사용자 권한으로 해석하지 않는다. 이 문서는 조건별 검증 스냅샷이며 최종 출시·설치 영수증이 아니다.

2026-11-13 검증 스냅샷의 기준 checkout은 `7b5ae4091641430d891e0c110c8efdb9a845a6ce` 위의 미커밋 통합 변경이며 제품 소스는 `0.27.0-candidate`다. `06a40a1`은 과거 고정 검사 보정 근거다. 이 갱신은 현재 소스·로컬 실행 로그·시각 검수 색인과 주 세션의 runtime 보고를 대조했다. 문서 작성자가 앱·브라우저·Figma를 다시 조작한 결과로 표시하지 않는다. 아래 실제 native·프로토타입 관찰은 주 세션 보고와 보호된 영수증을 연결한 범위다. Codex 설치 플러그인은 아직 `0.26.3`이며 후보 소스 runtime과 구분한다.

## 판정과 증거

- **코드 연결**: 구현·검사 위치 확인. 실행 통과를 뜻하지 않는다. 관련 검사 파일 하나가 조건 전체를 보장하지 않는다.
- **보고 관찰**: 주 세션 또는 담당 작업자의 실제 실행 보고. 문서 작성자의 재실행으로 표시하지 않는다.
- **대기**: 현재 해당 조건 전체의 결과·직접 관찰이 연결되지 않았다. 실패도 통과도 아니다.
- **부분 확인·전체 대기**: 연결한 자동 검사·getter·직접 조작의 범위만 확인했다. 나머지 항목과 보존 검사까지 확보하기 전에는 조건 전체를 통과로 표시하지 않는다.
- **통과(명시 범위)**: 기능서 조건이 요구하는 실제 getter·UI·서버·고정 fixture의 범위와 보존 항목을 확인했다. 자동 검사와 GUI 관찰을 구분하며 조건 밖 설치·앱 전체 영속 연결을 추가 요구하지 않는다. 다른 조건이나 출시 전체로 확대하지 않는다.

각 판정은 위 기록일·기준 소스와 아래 실행 이력에 연결한다. native 관찰은 실제 0.27 후보 runtime, 로컬 검사 관찰은 해당 공개 fixture 범위다. 실제 GUI 요구가 없는 조건에 GUI·설치를 임의로 추가하지 않으며 자동 검사를 실제 native 관찰로 표시하지 않는다. 명령/조작·기대/실제 결과와 안전한 증거는 행·아래 요약에 연결한다. private 자료는 원시 경로·토큰·계정 비밀 대신 안전한 요약만 공개한다. 캡처 개수·파일 존재·검사 이름·Wiki verify는 실제 인수 증거를 대신하지 않는다.

## REQ와 구현 경로

기능서에서 코드로 추출한 범위는 **45 REQ / 45 AC**다. 각 RD의 REQ 5개와 AC 5개를 생략 없이 유지한다. 아래 구현 경로는 해당 REQ 전체를 검토할 위치이며 REQ 충족은 관련 AC의 실제 범위와 함께 판단한다.

| 기능서·REQ 범위 | 현재 구현 경로 | 상태 |
| --- | --- | --- |
| [RD-01 기능서](RD-01-components/feature.md), `RD-01-REQ-01`–`RD-01-REQ-05` | [code.js](../../figma-bridge/code.js), [direction_review.js](../../figma-bridge/direction_review.js), [design_system.py](../../tools/design_system.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-02 기능서](RD-02-layer-structure/feature.md), `RD-02-REQ-01`–`RD-02-REQ-05` | [direction_review.js](../../figma-bridge/direction_review.js), [design_directions.py](../../tools/design_directions.py), [native_semantic_read.js](../../figma-bridge/native_semantic_read.js) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-03 기능서](RD-03-task-dependencies/feature.md), `RD-03-REQ-01`–`RD-03-REQ-05` | [dependencyView.mjs](../../panel-ui/src/dependencyView.mjs), [Workspace.jsx](../../panel-ui/src/Workspace.jsx), [figma_workspace.py](../../tools/figma_workspace.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-04 기능서](RD-04-selective-sync/feature.md), `RD-04-REQ-01`–`RD-04-REQ-05` | [graph_token_sync.js](../../figma-bridge/graph_token_sync.js), [GraphPanel.jsx](../../panel-ui/src/GraphPanel.jsx), [graph_sync.py](../../tools/graph_sync.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-05 기능서](RD-05-asset-inventory/feature.md), `RD-05-REQ-01`–`RD-05-REQ-05` | [assetInventory.mjs](../../panel-ui/src/assetInventory.mjs), [Workspace.jsx](../../panel-ui/src/Workspace.jsx), [input_effect.py](../../tools/input_effect.py), [figma_workspace.py](../../tools/figma_workspace.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-06 기능서](RD-06-native-read/feature.md), `RD-06-REQ-01`–`RD-06-REQ-05` | [native_semantic_read.js](../../figma-bridge/native_semantic_read.js), [figma_draft.py](../../tools/figma_draft.py), [graph_sync.py](../../tools/graph_sync.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-07 기능서](RD-07-runtime-boundaries/feature.md), `RD-07-REQ-01`–`RD-07-REQ-05` | [workspace_transport.js](../../figma-bridge/workspace_transport.js), [workspace_control.js](../../figma-bridge/workspace_control.js), [figma_workspace.py](../../tools/figma_workspace.py) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-08 기능서](RD-08-operation-lifecycle/feature.md), `RD-08-REQ-01`–`RD-08-REQ-05` | [workspace_control.js](../../figma-bridge/workspace_control.js), [workspace_host.js](../../figma-bridge/workspace_host.js), [figma_control.py](../../tools/figma_control.py), [Workspace.jsx](../../panel-ui/src/Workspace.jsx) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |
| [RD-09 기능서](RD-09-audit-log/feature.md), `RD-09-REQ-01`–`RD-09-REQ-05` | [audit_log.js](../../figma-bridge/audit_log.js), [DiagnosticExport.jsx](../../panel-ui/src/DiagnosticExport.jsx), [GraphPanel.jsx](../../panel-ui/src/GraphPanel.jsx), [Workspace.jsx](../../panel-ui/src/Workspace.jsx) | 연결된 AC 범위 통과; REQ 구현 범위는 별도 |


**REQ 구현의 한계:** RD-01-REQ-04의 optional label/icon을 위한 BOOLEAN·INSTANCE_SWAP 양성 생성은 첫 구현 범위에 없다. 현재는 TEXT·선언된 독립 축·원문 usage를 지원한다. `componentSwapTargets`는 배열 형태를 검사하지만 반환값을 생성에 사용하지 않으며 producer schema에도 optional icon property가 없다. AC-05의 미선언 조합·swap 생성 금지 통과를 선언된 swap 양성 구현으로 해석하지 않는다. 확장은 [NF-01](../next-roadmap/NF-01-component-families.md)의 PROPOSED 범위다. 아래 45 REQ ID는 추적 범위이며 전체 양성 기능 완료 선언이 아니다.

## AC별 매트릭스

아래 검사 링크와 [실제 관찰 요약](../../apps/little-hands/design/VERIFICATION.md)·[native QA 집계](../../apps/little-hands/design/native-qa-summary.json)는 각 조건의 근거다. 독립 검토가 확인한 기능서 원문의 범위로 판정하며 조건 밖 요구를 덧붙이지 않는다. 전체 출시 인수를 뜻하지 않는다. 현재 집계는 아래 명시된 fixture/runtime 범위에서 AC 45개 통과·부분 확인 0개·대기 0개다. 45 REQ의 모든 양성 기능 구현을 뜻하지 않는다. 새 앱 브라우저 동작은 플러그인 패널 관찰을 대신하지 않는다. 조건 문구는 기능서 원문이며 구현 경로는 위 REQ 표와 같다.

### RD-01

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-01-AC-01** — 한 main을 참조하는 세 instance에 서로 다른 문구가 보이고, main의 TEXT 정의와 label.componentPropertyReferences가 실제 getter에서 맞는다. | [test_figma_bridge.py](../../tests/test_figma_bridge.py) | R7 원본의 같은 main을 참조하는 세 instance의 다른 label·TEXT 정의·componentPropertyReferences를 실제 getter로 확인했다. 후속 정상 readDraft에서도 유지됐다. 보호된 r7-actual-text-property-evidence.json 및 앱 검증 요약. | 통과(명시 범위) |
| **RD-01-AC-02** — 같은 의미·구조에서 지원된 너비만 다른 세 사용처는 같은 main ID를 공유하며 각 렌더 너비는 원본과 같다. | [semantic_component_reuse_oracle.cjs](../../tests/semantic_component_reuse_oracle.cjs) | 실제 앱 set 복사본의 세 instance가 같은 Solid main을 공유하고 원래 설정한 180/240/300 렌더 너비를 유지했다. component reuse oracle의 구조 보존 검사와 함께 확인했다. | 통과(명시 범위) |
| **RD-01-AC-03** — 구조가 다른 fixture는 별도 main을 유지하고 기존 시각 회귀·token binding을 통과한다. | [semantic_component_reuse_oracle.cjs](../../tests/semantic_component_reuse_oracle.cjs), [test_graph_token_sync.cjs](../../tests/test_graph_token_sync.cjs) | 구조 차이 fixture의 별도 main·시각 회귀·token binding oracle을 통과했다. 조건은 구조 fixture 검사이며 모든 구조 fixture의 GUI 재생을 추가 요구하지 않는다. | 통과(명시 범위) |
| **RD-01-AC-04** — 같은 패킷 재실행 후 main/set/instance 수와 ID가 유지된다. 사용자가 바꾼 instance override를 초기화하지 않는다. | [test_figma_bridge.py](../../tests/test_figma_bridge.py) | R7 실제 instance opacity를 0.9로 편집한 뒤 같은 패킷 재실행에서 모든 ID·개수와 override가 유지됐다. 숫자는 1로 복원하고 정상 native 검증이 통과했으나 explicit opacity flag는 보관된 R7에 남는다. 새 R8은 동일 4,820개 ID·페이지 재사용, 15.502초·opacity override 0건을 확인했다. | 통과(명시 범위) |
| **RD-01-AC-05** — 선언하지 않은 variant 조합·사용 설명·swap target은 만들어지지 않는다. | [variant_axes_oracle.cjs](../../tests/variant_axes_oracle.cjs), [rd01_import_axes_acceptance.cjs](../../tests/rd01_import_axes_acceptance.cjs) | R8 실제 두 set의 정의는 TEXT와 Visual뿐이며 Visual 각각 12개가 control_styles 선언과 일치했다. 두 set을 실제 Component Configuration에서 열어 description·link가 모두 빈 값임을 확인했다. 미선언 BOOLEAN/SWAP·조합·설명을 만들지 않았다. 선언된 optional property 양성 구현은 뜻하지 않는다. | 통과(명시 범위) |

### RD-02

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-02-AC-01** — 선언한 카드·행·장식 묶음이 각각 Frame·Auto Layout Frame·Group으로 실제 트리에 나타난다. | [rd02_container_placement_oracle.cjs](../../tests/rd02_container_placement_oracle.cjs), [grouping-qa.json](../../apps/little-hands/design/grouping-qa.json) | 현재 producer의 R8 정상 검토·실제 getter에서 44개 화면의 선언된 Frame·Auto Layout·정적 Group 2개를 확인했다. 공개 grouping-qa와 실제 후보의 overlay가 일치했다. | 통과(명시 범위) |
| **RD-02-AC-02** — 부모 추가 전후 모든 leaf의 absolute bounding box, 원래 화면 clipping과 prototype 왕복이 유지된다. | [rd02_container_readback_oracle.cjs](../../tests/rd02_container_readback_oracle.cjs), [grouping-qa.json](../../apps/little-hands/design/grouping-qa.json) | R7→R8 제품 leaf 3,171개의 absolute bbox 필드 차이 0, 기존 Frame clip 550개 동일, 반응 노드 314개(제품 312·palette 2)의 semantic 연결 동일을 확인했다. R7 실제 prototype 왕복 관찰과 R8 정상·순수 검증을 연결한다. | 통과(명시 범위) |
| **RD-02-AC-03** — 문구 증가와 부모 resize에서 선언된 hug/fill/fixed 관계가 유지되며 사용자 instance가 detach되지 않는다. | [rd02_container_sizing_oracle.cjs](../../tests/rd02_container_sizing_oracle.cjs) | 실제 복사본 parent FIXED 360→420·HUG 높이, child FILL 340→400·HUG 48과 label HUG/HUG의 한글 증가를 확인했다. main/instance 연결을 유지했다. 실험 label 5개·너비·높이·main·parent를 복원하고 wrapper를 제거했다. | 통과(명시 범위) |
| **RD-02-AC-04** — cycle·중복 부모·지원하지 않는 Group 속성은 쓰기 전에 거절된다. | [test_rd02_layer_normalize.py](../../tests/test_rd02_layer_normalize.py) | 직접 validation fixture에서 cycle·중복 부모·미지원 Group 속성이 쓰기 전에 거절되고 쓰기가 없었다. native GUI 관찰과 구분한다. | 통과(명시 범위) |
| **RD-02-AC-05** — 기존 container 없는 패킷은 동일한 트리와 geometry로 동작한다. | [test_rd02_layer_fixtures.py](../../tests/test_rd02_layer_fixtures.py), [rd02_container_placement_oracle.cjs](../../tests/rd02_container_placement_oracle.cjs) | container 없는 기존 패킷의 직접 compatibility fixture와 placement oracle에서 동일 트리·geometry를 확인했다. 고정 fixture 범위의 호환성 판정이다. | 통과(명시 범위) |

### RD-03

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-03-AC-01** — 선행 입력→검토→가져오기 세 작업의 명시적 두 edge만 보인다. 같은 project의 무관한 작업에는 선이 없다. | [test_rd03_task_fixtures.py](../../tests/test_rd03_task_fixtures.py), [test_rd03_dependency_view.py](../../tests/test_rd03_dependency_view.py) | 실제 브라우저 fixture 560/320에서 명시적 입력→검토→가져오기 두 edge와 같은 project 독립 작업의 edge 0개를 확인했다. 실제 catalogue 4개 subset도 현재 edge 2개·독립 0개였다. literal import는 표시 fixture이며 새 native import 실행이 아니다. | 통과(명시 범위) |
| **RD-03-AC-02** — 선행 revision 변경 시 후속 작업은 stale로 표시되며 자동 실행되지 않는다. | [test_rd03_dependency_freshness.py](../../tests/test_rd03_dependency_freshness.py), [finalize_dependency_publication.py](../../tests/finalize_dependency_publication.py) | 현재/선행 revision 변경에 따른 stale native UI와 읽기 전용 freshness 검사에서 stale 표시·자동 실행 없음을 확인했다. | 통과(명시 범위) |
| **RD-03-AC-03** — cycle와 없는 artifact/hash는 prepare/publish 전에 거절된다. | [test_rd03_task_dependencies.py](../../tests/test_rd03_task_dependencies.py), [finalize_dependency_publication.py](../../tests/finalize_dependency_publication.py) | 실제 로컬 publisher에서 cycle·없는 artifact·hash 불일치가 prepare/publish 전에 거절되고 게시 상태가 보존됐다. 로컬 실행 근거다. | 통과(명시 범위) |
| **RD-03-AC-04** — edge 없는 기존 task는 독립 작업으로 보이고 기존 실행·추천 동작이 유지된다. | [test_rd03_identity_boundary.py](../../tests/test_rd03_identity_boundary.py), [test_rd03_task_fixtures.py](../../tests/test_rd03_task_fixtures.py) | 실제 독립 task receipt state ok와 기존 추천 로직이 edge 유무에 따라 바뀌지 않는 순수 검사를 확인했다. catalogue 독립 작업은 edge 0개이며 실행·추천 계약이 유지됐다. | 통과(명시 범위) |
| **RD-03-AC-05** — 320px에서 목록형 대체 보기, 키보드로 node/edge 이동, 같은 정보의 텍스트 설명을 제공한다. | [test_rd03_dependency_view.py](../../tests/test_rd03_dependency_view.py), [test_panel_components.py](../../tests/test_panel_components.py) | 실제 catalogue 브라우저 320px에서 목록·키보드 Enter 뒤 H3 focus·같은 전체 텍스트 관계 6개를 확인했다. scrollWidth/clientWidth 305/305였다. CSS 320px에서 SVG 미표시, 560px에서 SVG 너비 497·overflow 없음도 확인했다. | 통과(명시 범위) |

### RD-04

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-04-AC-01** — 서로 독립적인 세 변경 중 두 개를 고르면 실제 해당 두 값만 바뀌고 나머지 값은 보존된다. | [test_rd04_selective_apply.py](../../tests/test_rd04_selective_apply.py), [test_graph_token_sync.cjs](../../tests/test_graph_token_sync.cjs) | 복사본 실제 native 3색 중 선택한 두 값만 바뀌고 세 번째 값·이전 marker가 보존됐다. partial 후 fresh full과 전체 pairing을 확인했다. 원본 앱 영속 SSOT 채택은 이 조건 밖이다. | 통과(명시 범위) |
| **RD-04-AC-02** — 선택 없음은 Apply를 비활성화하고 서버에서도 거절한다. | [test_rd04_selection_rows.py](../../tests/test_rd04_selection_rows.py), [test_graph_token_sync.cjs](../../tests/test_graph_token_sync.cjs), [finalize_selective_sync.py](../../tests/finalize_selective_sync.py) | generated host·legacy selection 검사와 실제 Figma UI에서 선택 0개일 때 Apply 비활성화 및 빈 선택 서버 거절을 확인했다. | 통과(명시 범위) |
| **RD-04-AC-03** — alias 종속을 반만 고를 수 없고 묶음의 실제 영향 대상이 보인다. | [test_rd04_selection_identity.py](../../tests/test_rd04_selection_identity.py), [test_rd04_component_fields.py](../../tests/test_rd04_component_fields.py), [finalize_selective_sync.py](../../tests/finalize_selective_sync.py) | generated host·legacy selection closure 검사가 alias 반쪽 선택을 거절하고 영향 target을 유지했다. 실제 UI에서도 두 그룹·partial 범위를 확인했다. | 통과(명시 범위) |
| **RD-04-AC-04** — 승인 뒤 graph/readback이 바뀌면 기존 before-value와 pin 검사에서 실패한다. | [test_graph_sync.py](../../tests/test_graph_sync.py), [test_graph_token_sync.cjs](../../tests/test_graph_token_sync.cjs), [finalize_selective_sync.py](../../tests/finalize_selective_sync.py) | generated host·고정 before-value/pin 검사에서 승인 뒤 graph/readback 변경을 쓰기 전에 거절했다. 실제 UI 취소·다시 열기와 partial 후 fresh full 관찰도 연결한다. | 통과(명시 범위) |
| **RD-04-AC-05** — 취소·키보드 선택·선택 변경·실패 복구와 JSON 결과의 범위가 일치한다. | [test_rd04_selection_rows.py](../../tests/test_rd04_selection_rows.py), [test_graph_panel.cjs](../../tests/test_graph_panel.cjs) | 실제 브라우저의 React·legacy 모두 취소/Escape 후 review focus·요청 0개, 키보드 세 그룹 해제 후 비활성·요청 0개를 확인했다. 선택 6개에서 실제 기록된 stale 오류와 정확한 다운로드를 replay하고 read의 실제 기록 JSON으로 복구했다. primary pair 해제 후 선택 4개의 적용 결과도 기록된 실제 partial JSON과 일치했다. 패널별 요청 3개(apply 2/read 1), replay 3·blocked 0·기록 pin 2개를 확인했다. browser replay와 별도의 실제 native partial/full 재계획·pairing 증거를 구분한다. | 통과(명시 범위) |

### RD-05

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-05-AC-01** — 중첩 CSS 두 개에서 같은 글꼴을 참조하면 목록은 한 자산과 두 출처를 보여준다. | [test_rd05_asset_freshness.py](../../tests/test_rd05_asset_freshness.py), [finalize_input_audit.py](../../tests/finalize_input_audit.py) | 실제 parser·rooted normal admission의 215개 자산에서 실제 font 한 개의 중첩 CSS 출처 두 개를 보존했다. 상태는 present 212·missing/rejected/external 각 1이며 실제 JPEG 205개를 포함한다. UI는 canonical React 목록 projection이다. | 통과(명시 범위) |
| **RD-05-AC-02** — 없는 로컬 사진은 404와 해당 상대 경로를 보여주고, 위험한 경로는 rejected로 보인다. | [test_rd05_html_input_record.py](../../tests/test_rd05_html_input_record.py), [test_input_effect_css.py](../../tests/test_input_effect_css.py) | 실제 rooted parser/admission에서 missing 로컬 사진의 404·상대 경로와 위험 경로 rejected를 확인하고 같은 상태를 canonical 목록 UI에서 확인했다. | 통과(명시 범위) |
| **RD-05-AC-03** — 외부 글꼴 URL은 external-unverified이며 패널을 열어도 fetch되지 않는다. | [test_rd05_asset_inventory.py](../../tests/test_rd05_asset_inventory.py), [test_rd05_browser_contrast.py](../../tests/test_rd05_browser_contrast.py) | 외부 font가 external-unverified로 표시되고 소유한 외부 trap의 fetch는 0개였다. 패널 목록 표시와 실제 네트워크 관찰이며 present를 렌더 성공으로 확대하지 않는다. | 통과(명시 범위) |
| **RD-05-AC-04** — 파일 추가·삭제·byte 변경 후 목록은 stale로 바뀌고 새 input record가 준비돼야 갱신된다. | [test_rd05_asset_freshness.py](../../tests/test_rd05_asset_freshness.py) | 실제 파일 추가·삭제·bytes 변경 각각 stale을 확인했다. 예전 input record로 prepare가 거절되고 새 record 준비 뒤 current가 됐다. | 통과(명시 범위) |
| **RD-05-AC-05** — 큰 목록을 검색·종류·상태로 좁힐 수 있고 키보드와 텍스트만으로 상태를 구분한다. | [test_rd05_asset_inventory.py](../../tests/test_rd05_asset_inventory.py), [test_panel_components.py](../../tests/test_panel_components.py) | 실제 215개 목록의 canonical React projection에서 검색·종류·상태 필터를 키보드로 조작하고 텍스트 상태를 구분했다. static 목록 projection 관찰이며 모든 workspace 제어를 실행했다는 뜻이 아니다. | 통과(명시 범위) |

### RD-06

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-06-AC-01** — 변화 없는 fixture에서 partial projection의 요청 필드는 full 결과와 같고, 부분 읽기임이 명시된다. | [rd06_summary_coverage.cjs](../../tests/rd06_summary_coverage.cjs), [rd06_read_comparison.cjs](../../tests/rd06_read_comparison.cjs), [finalize_discovery_summary.cjs](../../tests/finalize_discovery_summary.cjs) | 실제 R7 summary 4,818개 노드의 width/height가 이전 full과 불일치 0개였다. 실제 패널·진단에 summary·complete false·주 페이지 coverage가 표시됐다. | 통과(명시 범위) |
| **RD-06-AC-02** — getter 호출 수가 의도한 필드 범위만큼 줄어든다. 실제 측정 전 wall-clock 개선율은 표시하지 않는다. | [rd06_full_getter_ledger.cjs](../../tests/rd06_full_getter_ledger.cjs), [rd06_read_comparison.cjs](../../tests/rd06_read_comparison.cjs) | 동일 fixture의 getter ledger·profile 비교에서 요청 필드만큼 호출 감소·값 일치를 측정했다. 실제 wall-clock 개선율은 주장하지 않는다. | 통과(명시 범위) |
| **RD-06-AC-03** — 추가·삭제·reparent·문구·style·variable·이미지 변경과 file/page 전환에서 stale cache를 재사용하지 않는다. | [rd06_fresh_read.cjs](../../tests/rd06_fresh_read.cjs), [finalize_reader_freshness_matrix.cjs](../../tests/finalize_reader_freshness_matrix.cjs) | 추가·삭제·reparent·문구·style·variable·이미지·file/page 전환을 열거한 14개 full/summary 쌍에서 최신 값·closure·이전 snapshot 보존을 확인했다. cache는 없으며 cache event integration을 검증했다고 주장하지 않는다. | 통과(명시 범위) |
| **RD-06-AC-04** — partial 결과로 graph import/apply/recovery를 시도하면 거절되거나 fresh full read를 수행한다. | [rd06_reject_partial.cjs](../../tests/rd06_reject_partial.cjs), [finalize_partial_consumers.cjs](../../tests/finalize_partial_consumers.cjs), [finalize_partial_consumers.py](../../tests/finalize_partial_consumers.py) | 실제 apply summary plan은 API 전에 거절됐다. 유효 plan에 위조 summary를 붙여도 실제 native getter를 사용하고 stale drift는 쓰기 0개였다. import 출력 파일 없음·control recovery의 summary 뒤 uncertainty 유지·유효 fresh full 뒤 reconcile을 4개 직접 검사로 확인했다. 실제 4,818개 summary의 일반 import/pair 거절·fresh full 진단 교체도 관찰했다. | 통과(명시 범위) |
| **RD-06-AC-05** — 기존 inline raster와 raster table 호환·paint/ref·원본 SHA 검사를 유지한다. | [test_native_raster_table.cjs](../../tests/test_native_raster_table.cjs), [graph_discovery_raster_oracle.cjs](../../tests/graph_discovery_raster_oracle.cjs), [test_native_raster_assets.py](../../tests/test_native_raster_assets.py) | inline raster/raster table의 직접 호환성·paint/ref·원본 SHA 행동 검사가 통과했다. 실제 native 시각 검수와 별개인 보존 검사다. | 통과(명시 범위) |

### RD-07

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-07-AC-01** — 기존 import/read/sync/native-edit/review 메시지 trace와 결과·오류가 구조 변경 전후 같아야 한다. | [test_rd07_runtime_boundary.py](../../tests/test_rd07_runtime_boundary.py), [rd07_transport_move.cjs](../../tests/rd07_transport_move.cjs), [finalize_runtime_contract_matrix.py](../../tests/finalize_runtime_contract_matrix.py) | runtime contract matrix의 3개 직접 검사와 2db4→199683f 역사 fixture body의 동등성은 전송 추출 범위에서 일치했다. 이후 protocol 2·용량 증가는 의도한 별도 변경이며 모든 과거 버전과 동일하다고 확대하지 않는다. | 통과(명시 범위) |
| **RD-07-AC-02** — 전송 모듈 하나만 바꿔도 runtime digest가 바뀌고 오래된 runtime의 쓰기는 차단된다. | [test_native_runtime_version.cjs](../../tests/test_native_runtime_version.cjs), [test_rd07_runtime_assembly.py](../../tests/test_rd07_runtime_assembly.py), [finalize_runtime_contract_matrix.py](../../tests/finalize_runtime_contract_matrix.py) | 전송만 바꿔 재게시하면 digest가 바뀌고 old mutation claim은 거절·current는 허용됐다. 실제 오래된 native identity를 유지한 재게시 뒤 쓰기 요청도 enqueue 전에 거절됐고 request 0개였다. | 통과(명시 범위) |
| **RD-07-AC-03** — 어느 task에도 다른 task의 private closure·capability·scope가 노출되지 않는다. | [test_rd07_public_symbols.py](../../tests/test_rd07_public_symbols.py), [test_rd07_bundle_kinds.py](../../tests/test_rd07_bundle_kinds.py), [finalize_runtime_contract_matrix.py](../../tests/finalize_runtime_contract_matrix.py) | 정상 publisher의 두 task 생성 bundle을 VM에서 실행해 private file/page/session·closure·scope 격리를 확인했다. 실제 native GUI의 모든 task 실행으로 표시하지 않는다. | 통과(명시 범위) |
| **RD-07-AC-04** — 실패·timeout·duplicate result·복구 경로가 기존과 동일하게 fail closed한다. | [test_workspace_control.cjs](../../tests/test_workspace_control.cjs), [test_workspace_publish_guard.py](../../tests/test_workspace_publish_guard.py) | HTTP fault·timeout·recovery fixture와 실제 terminal 동일 결과 200/상충 409 및 오래된 runtime 쓰기 차단에서 fail closed를 확인했다. | 통과(명시 범위) |
| **RD-07-AC-05** — 실제 생성 bundle을 실행하는 검사와 source/생성 재빌드 비교를 모두 통과한다. | [test_rd07_bundle_kinds.py](../../tests/test_rd07_bundle_kinds.py), [test_rd07_runtime_assembly.py](../../tests/test_rd07_runtime_assembly.py) | 공유 소스 조립·모든 5개 task kind의 실제 생성 bundle 실행과 source/생성 재빌드 비교 검사가 통과했다. Codex 설치 갱신은 이 조건 밖 별도 출시 검증이다. | 통과(명시 범위) |

### RD-08

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-08-AC-01** — claim 전 timeout과 claim 후 timeout이 다르게 표시되며 어느 경우도 native-started를 꾸며내지 않는다. | [test_rd08_operation_transitions.py](../../tests/test_rd08_operation_transitions.py), [test_rd08_native_started.py](../../tests/test_rd08_native_started.py), [finalize_lifecycle_oracle.py](../../tests/finalize_lifecycle_oracle.py), [finalize_lifecycle_transport.cjs](../../tests/finalize_lifecycle_transport.cjs) | 실제 로컬 서버·저장소 및 host fixture에서 claim 전후 timeout의 phase 차이와 꾸민 native-started 없음을 확인했다. | 통과(명시 범위) |
| **RD-08-AC-02** — native 성공 뒤 HTTP 결과 전달 실패는 uncertain으로 남고 같은 mutation이 자동 재실행되지 않는다. | [test_rd08_restart_delivery.py](../../tests/test_rd08_restart_delivery.py), [finalize_lifecycle_oracle.py](../../tests/finalize_lifecycle_oracle.py), [finalize_lifecycle_transport.cjs](../../tests/finalize_lifecycle_transport.cjs) | native 성공 callback 뒤 HTTP 전달을 실패시키는 fault fixture와 실제 서버·저장소 검사에서 uncertain 보존·자동 mutation 재실행 없음을 확인했다. 합성 callback을 실제 Figma 장애 관찰로 표시하지 않는다. | 통과(명시 범위) |
| **RD-08-AC-03** — 올바른 scope의 read만 원래 uncertainty와 연결되며 다른 file/page/revision의 read는 차단을 해제하지 않는다. | [test_figma_control.py](../../tests/test_figma_control.py), [finalize_lifecycle_oracle.py](../../tests/finalize_lifecycle_oracle.py) | 실제 서버·저장소 recovery fixture에서 올바른 file/page/revision read만 원래 uncertainty와 연결되고 다른 scope는 해제하지 않음을 확인했다. | 통과(명시 범위) |
| **RD-08-AC-04** — 중복 결과는 기존 terminal receipt와 정확히 같을 때만 결정적으로 처리하고 상충 결과를 거절한다. | [test_workspace_control.cjs](../../tests/test_workspace_control.cjs), [test_figma_control.py](../../tests/test_figma_control.py), [finalize_terminal_result.py](../../tests/finalize_terminal_result.py) | 고정 7개 검사에서 변경 전 예상 assertion 실패 5개·변경 후 7개 통과, 관련 52개 검사 통과 및 독립 검토를 확인했다. 새 소스 서버·재개한 plugin의 실제 full 읽기 결과를 인증 HTTP로 그대로 재전송하면 원래 ACK 200, raw JSON 끝 newline 변경은 409였다. 두 호출 모두 receipt/readback/uncertainty hash·mtime이 보존됐고 native 쓰기가 없었다. | 통과(명시 범위) |
| **RD-08-AC-05** — rollback conflict 각 항목이 정확한 관측 값과 plan hash를 보존하며 legacy history는 phase unknown으로 보인다. | [test_rd08_conflict_detail.py](../../tests/test_rd08_conflict_detail.py), [test_rd08_journal_history.py](../../tests/test_rd08_journal_history.py), [workspace_history_failure_oracle.cjs](../../tests/workspace_history_failure_oracle.cjs), [finalize_lifecycle_oracle.py](../../tests/finalize_lifecycle_oracle.py) | 실제 journal·clientStorage fixture에서 각 conflict의 observed 값·plan hash 보존과 legacy phase unknown을 확인했다. 실제 Figma GUI 재현과 구분한다. | 통과(명시 범위) |

### RD-09

| 조건 | 관련 검사·고정 oracle | 확인 근거와 범위 | 상태 |
| --- | --- | --- | --- |
| **RD-09-AC-01** — 마크다운 본문과 그 안의 JSON이 같은 진단 사실이다. 텍스트 복사는 그 마크다운이다. | [rd09_audit_log.cjs](../../tests/rd09_audit_log.cjs), [finalize_diagnostic_version.cjs](../../tests/finalize_diagnostic_version.cjs) | 실제 패널의 신뢰된 클릭으로 clipboard 2,464자가 보이는 Markdown·MD 다운로드·fenced JSON·JSON 다운로드와 일치했고 버전은 0.27이었다. 초기 키보드 복사의 빈 값 근거는 보존하고 재검증으로 해소했다. | 통과(명시 범위) |
| **RD-09-AC-02** — 비밀값은 기록에 남지 않고, 노드 ID·리비전·오류·작업 식별자는 남는다. | [rd09_audit_log.cjs](../../tests/rd09_audit_log.cjs), [finalize_audit_privacy.cjs](../../tests/finalize_audit_privacy.cjs), [finalize_input_audit.py](../../tests/finalize_input_audit.py) | 실제 Figma 진단 내보내기·redaction 행동 검사에서 비밀 비노출과 진단 ID/리비전/오류/작업 식별자 보존을 확인했다. | 통과(명시 범위) |
| **RD-09-AC-03** — 요약 읽기와 전체 읽기의 범위가 구분되고, 읽기가 없으면 그 검사가 관찰되지 않았다고 적힌다. | [rd09_audit_log.cjs](../../tests/rd09_audit_log.cjs), [finalize_discovery_summary.cjs](../../tests/finalize_discovery_summary.cjs) | 실제 Figma no-read/full/summary 진단에서 미관찰 표기와 정확한 범위를 확인했다. summary→full 뒤 node·variable·collection 내용이 원본 full과 일치했다. | 통과(명시 범위) |
| **RD-09-AC-04** — 그래프 패널의 복사·저장은 문서를 바꾸지 않고 네이티브 쓰기를 보내지 않으며 페어링을 바꾸지 않는다. | [rd09_audit_log.cjs](../../tests/rd09_audit_log.cjs), [finalize_input_audit.py](../../tests/finalize_input_audit.py) | 실제 Figma 진단 저장 전후 문서·pairing·node/variable/collection 관측이 유지됐고 읽기 전용 경로·mutation 요청 없음 검사를 확인했다. | 통과(명시 범위) |
| **RD-09-AC-05** — 실제 Figma 패널에서 내보내기를 확인하기 전에는 그 관찰을 통과로 기록하지 않는다. | [rd09_audit_log.cjs](../../tests/rd09_audit_log.cjs), [finalize_diagnostic_version.cjs](../../tests/finalize_diagnostic_version.cjs) | 실제 Figma 패널에서 내보내기·파일 내용을 직접 확인했다. 0.27 버전, 보이는 Markdown·fenced JSON·저장 파일 일치를 확인했으며 clipboard 전달 관찰과 구분한다. | 통과(명시 범위) |

## 독립 앱: 작은손 커피공방

계약은 [ARCHITECTURE.md](../../apps/little-hands/ARCHITECTURE.md), [README.md](../../apps/little-hands/README.md)에 있다. Django 5.2/PostgreSQL 17 서버·DB가 정본인 회원/운영자 예약 앱이다. 온라인 결제·외부 메시지 발송은 범위가 아니다. 운영 가능한 패키지와 실제 공개 운영 인수를 구분한다.

| 검증 범위 | 소스·검사 | 현재 보고 및 한계 |
| --- | --- | --- |
| 인증·RBAC·CSRF·회원 격리 | [views.py](../../apps/little-hands/booking/views.py), [forms.py](../../apps/little-hands/booking/forms.py), [settings.py](../../apps/little-hands/config/settings.py), [middleware.py](../../apps/little-hands/config/middleware.py), [test_booking.py](../../apps/little-hands/booking/tests/test_booking.py) | 주 세션은 실제 로그인·회원 staff 403·타인 예약 404를 보고했다. 최종 PostgreSQL 17 앱 실행의 58개 통과 로그를 확인했다. CSRF·signup 권한 주입·method guard는 해당 suite의 자동 검사이며 브라우저 직접 관찰과 구분한다. |
| 예약·검토·영속·취소·일정 변경·409 | [services.py](../../apps/little-hands/booking/services.py), [models.py](../../apps/little-hands/booking/models.py), [test_booking.py](../../apps/little-hands/booking/tests/test_booking.py) | 주 세션은 두 명/90,000원 검토→확정→영속 확인, 취소·일정 변경, 두 탭 stale 409를 보고했다. 58개 앱 suite 통과를 확인했다. 변경·취소 및 대상 변경 뒤 멱등 재생 검사를 포함하며 공개 운영 트래픽 검증은 아니다. |
| transaction·잠금·FIFO·멱등성 | [services.py](../../apps/little-hands/booking/services.py), [test_booking.py](../../apps/little-hands/booking/tests/test_booking.py) | advisory transaction lock·회차 ID 순 row lock·FIFO head group 보존을 소스에서 확인. 동시 마지막 좌석·중복 요청·cancel/reschedule 경쟁을 포함한 PostgreSQL 앱 suite 58개가 통과했다. 단일 브라우저 흐름만으로 동시성을 증명하지 않는다. |
| 운영 회차·정원·가격·정책 | [services.py](../../apps/little-hands/booking/services.py), [0001_initial.py](../../apps/little-hands/booking/migrations/0001_initial.py), [0003_session_cancellation_policy.py](../../apps/little-hands/booking/migrations/0003_session_cancellation_policy.py), [test_booking.py](../../apps/little-hands/booking/tests/test_booking.py) | 주 세션은 overlap 409·입력 보존·회차 생성, 정원 4→5의 대기 승급, 기존 45,000원 유지/새 48,000원을 보고했다. 정책 snapshot·exclusion·rollback 및 이동 후 원래 예약 조건 보존을 포함한 최종 앱 suite 58개가 통과했다. |
| 알림·감사 | [services.py](../../apps/little-hands/booking/services.py), [views.py](../../apps/little-hands/booking/views.py), [audit_display.py](../../apps/little-hands/booking/templatetags/audit_display.py), [test_audit_display.py](../../apps/little-hands/booking/tests/test_audit_display.py), [test_booking.py](../../apps/little-hands/booking/tests/test_booking.py) | 주 세션은 대기 등록·서로 다른 알림 읽음 처리를 보고했다. stored 감사 값·escape·legacy facts와 변경/승급 알림 검사를 포함한 앱 suite 58개 통과를 확인했다. 외부 메시지 발송은 실행하지 않는다. |
| 모바일·키보드 표 스크롤 | [app.css](../../apps/little-hands/static/littlehands/app.css), [audit.html](../../apps/little-hands/templates/staff/audit.html), [session_table.html](../../apps/little-hands/templates/staff/session_table.html), [roster_table.html](../../apps/little-hands/templates/staff/roster_table.html) | 주 세션은 모바일 표 scrollWidth/clientWidth 615/327, tabindex=0, 키보드 가로 이동 +6px를 보고했다. 앱의 해당 표 상태만의 관찰이며 전체 접근성·320px 플러그인 인수가 아님. |
| migration/runtime role·journal 불변 | [roles.sql](../../apps/little-hands/deploy/roles.sql), [grants.sql](../../apps/little-hands/deploy/grants.sql), [verify.sql](../../apps/little-hands/deploy/verify.sql), [0002_immutable_records.py](../../apps/little-hands/booking/migrations/0002_immutable_records.py), [test_deployment.py](../../apps/little-hands/tests/test_deployment.py) | 담당자는 runtime role journal UPDATE/DELETE/TRUNCATE·DDL 거절(SQLSTATE 42501)을 보고했다. owner 앱 테스트는 runtime 권한 검사 대체 불가. |
| 컨테이너·보안·health·복원 | [Dockerfile](../../apps/little-hands/Dockerfile), [compose.yaml](../../apps/little-hands/compose.yaml), [tests.py](../../apps/little-hands/config/tests.py), [healthcheck.py](../../apps/little-hands/deploy/healthcheck.py), [test_deployment.py](../../apps/little-hands/tests/test_deployment.py) | 최종 candidate 이미지 재빌드 성공 로그를 확인했다. arm64 환경·runtime·HTTPS용 설정·loopback health 및 별도 DB dump/restore 성공은 담당자 보고다. public DNS/TLS·Linux ACL·amd64는 미검증. 내부 health는 실제 TLS 증거가 아님. |
| 실제 화면→Figma | [README.md](../../apps/little-hands/design/README.md), [source.py](../../apps/little-hands/design/source.py), [measure.js](../../apps/little-hands/design/measure.js), [test_source.py](../../apps/little-hands/design/test_source.py), [graph.json](../../apps/little-hands/design/graph.json), [source-status.json](../../apps/little-hands/design/source-status.json) | [시각 검수 색인](../../apps/little-hands/design/visual-review-images/index.json)의 44개 상태·viewport 기록 모두 primary-agent 검수 표시가 있다. 이미지는 47개이며 긴 화면 세 개의 top/bottom 쌍을 포함한다. inert HTML의 실제 브라우저 렌더 검수이고 business 실행은 별도다. R7 실제 full getter 검토가 통과했고 아래 일부 native 프로토타입 조작을 주 세션이 확인했다. source-status의 선언 상태와 실제 관측을 구분하며 창작 품질·사람의 production 승인은 대기다. |

## 앱 소스와 시각 검수의 현재 근거

최종 앱 로그에서 `Ran 58 tests`와 `OK`, system check 0건을 확인했다. PostgreSQL 17 실행 환경과 명령 수행은 주 세션 보고이며 문서 작성자가 서버 검사를 재실행하지 않았다. 이미지 빌드 로그는 `0.27.0-candidate` export 완료를 기록한다. 원시 로그에는 로컬 경로와 테스트 요청이 있으므로 공개 문서에는 안전한 결과만 요약한다.

[quality.json](../../apps/little-hands/design/quality.json)은 오류 0건·경고 13건이고 strict 검사는 아니다. [R4→R5 회귀 비교](../../apps/little-hands/design/control-reuse-regression-r4-r5.json)는 12개 공유 component family, viewport별 12개로 총 24개 main 선언을 기록한다. 이전 492개 main 선언을 줄이면서 instance 선언 492개와 action 기록 246개, 44개 capture·HTML SHA 쌍, prototype binding과 layer box를 보존했다. 이 수치는 정적 authored-source 비교다. 후속 R7 실제 getter에서는 main 24개·set 2개·instance 494개(화면 컨트롤 492개·palette 2개)를 별도로 확인했다. 정적 비교와 native 관측을 합쳐 전체 재사용 인수로 표시하지 않는다.

[source-status.json](../../apps/little-hands/design/source-status.json)의 current source epoch와 [graph.json](../../apps/little-hands/design/graph.json)의 인수 상태를 분리한다. 44개 시각 검수 보고는 디자인 선택·production 승인과 native 편집·prototype 왕복 인수를 자동 완료하지 않는다.

## 출시 전 실행 결과 연결 지점

아래 전체 suite는 terminal 결과 멱등성 수정 이전의 안정 실행 이력이다. 원시 로그와 native 식별자는 공개하지 않는다. 수정 뒤 고정 7개·관련 52개 검사와 실제 HTTP 중복 전달은 별도로 확인했다. 수정 뒤 전체 suite와 push 이후 CI는 아직 결과를 연결하지 않았으며 미리 성공으로 선언하지 않는다.

| 실행 묶음 | 최종 결과 | 범위·남은 경계 |
| --- | --- | --- |
| 앱 PostgreSQL | 58개 실행·OK·system check 문제 0건 | 실제 PostgreSQL 실행. runtime DB role·공개 운영 환경 인수는 별도다. |
| 패키지 | 4개 실행·OK | 컨테이너/권한/복원 관찰은 별도다. |
| 플러그인 Node 전체 | 289개 중 288 통과·1 skip·실패 0 | terminal 결과 멱등성 수정 전 안정 실행이다. skip은 미실행이며 수정 뒤 전체 결과가 아니다. |
| 플러그인 Python 전체 | 1107개 실행·OK·skip 2 | terminal 결과 멱등성 수정 전 안정 실행이다. skip 2개는 미실행이며 수정 뒤 결과는 별도다. |
| finalize Python | 58개 실행·OK | 플러그인 Python 전체 및 앱 PostgreSQL의 58개와 별도 실행이다. |
| demo | 2개 실행·OK | demo 범위의 자동 검사다. |
| 독립 코드 검토 | 새 설명 보드·binding·부모 처리 4개 모듈 검토에서 P1/P2 없음이라는 주 세션 보고 | 40개 Python·8개 spec·3개 container oracle 범위의 근거. 검토 밖 diff와 이후 변경, 제품 인수 전체를 보장하지 않는다. |
| native runtime | R7 후보 runtime의 생성·재실행·최종 discovery 영수증이 모두 ok | Codex 설치는 0.26.3이다. 후보 release·push·설치 후 검증은 대기다. |

## R7 실제 native 및 제한된 왕복 근거

[실제 검증 요약](../../apps/little-hands/design/VERIFICATION.md)과 [native QA 집계](../../apps/little-hands/design/native-qa-summary.json)에 안전한 범위·원시 근거 SHA256을 연결한다. R7 normal full getter는 4,818개 노드·30,103,016바이트이며 검토 결과 passed다. 44개 화면, prototype getter 312개, 복귀 getter 110개, 설명 보드 연결 target 536개를 확인했다. main 24개·set 2개·instance 494개·variable 69개·collection 1개는 실제 getter 집계다. getter 검사는 모든 링크의 GUI 재생이나 사람의 production admission이 아니다.

동일 패킷 재실행은 기존 페이지를 재사용하고 전체 노드 ID 집합을 유지했으며 순수 native 검사가 통과했다. 재실행 영수증 경과 시간은 14.99초다. 최초 생성과 동일한 작업량의 성능 배수로 표시하지 않는다. ID 대조와 별개로 실제 R7 opacity 편집·재실행 보존 및 후속 R8 clean 검사를 아래에 연결했다.

복사한 실제 앱 component set에서 instance 5개를 만든 별도 실험이 있다. 그중 3개는 같은 Solid main을 참조하며 서로 다른 TEXT property·보이는 문구와 너비 180/240/300을 유지했다. 복사한 main의 글자색이 3개 label에 전파되고 문구·너비가 보존됐으며 시각적 색을 복원했다. 복사본 binding은 의도적으로 분리했으므로 binding 구조 전체 복원을 주장하지 않는다. 이 복사본 색 실험은 원본 R7을 바꾸지 않았다. 이후 별도의 R7 실제 opacity override 보존 실험은 수행했으므로 R7 전체가 손대지 않은 상태였다고 표시하지 않는다.

제한된 Graph SSOT 실험은 복사한 라이브러리의 brand·navigation·primary 3색과 실제 Django 응답의 임시 외부 CSS 소비자만 대상으로 했다. primitive root 3개 중 2개(선택 manifest 4행)를 적용하여 두 값 변경·세 번째 값과 이전 graph marker 보존을 확인했다. partial pairing은 거절됐고 나머지는 최신 full getter·새 plan·CAS 적용 후 전체 pairing했다. 실제 native variable 편집에서 한 필드만 graph로 가져와 웹 소비자 3개에 반영했고 unsupported sizing 5건은 그대로 남겼다. 원래 값·전체 pairing·초기 graph bytes·template hash를 복원하고 임시 CSS/MJS를 제거했다. 최종 실제 Django 응답은 graph attribute·overlay link가 각각 0개이며 사진이 로드됐다. 원본 앱 44개 화면의 영속 Graph SSOT 채택은 이 실험의 범위 밖이며 RD-04-AC-01에 별도 조건으로 추가하지 않는다.

주 세션은 CUA로 실제 R7 Figma 프로토타입의 desktop 홈→로그인→홈, mobile 홈→로그인→홈을 직접 열어 왕복했다. mobile 운영 dashboard의 세로 스크롤과 중첩 표를 강좌/날짜에서 정원/확정/대기/상태/관리 열까지 오른쪽으로 드래그한 뒤 왼쪽으로 복원했다. 보호된 화면·복귀 기록이 있다. 이 관찰은 정적 프로토타입 탐색이며 인증·POST 실행이나 312개 링크 전체의 GUI 재생이 아니다. 원본 44개 이미지·47개 실제 image artifact의 시각 검수는 주 세션 보고이며 사람의 창작 품질 승인은 아직 없다. 실제 GUI 관찰은 위 경로와 표 드래그 범위에 한정한다.

## R8 현재 producer와 보존 근거

R8 정상 producer의 실제 생성은 485.154초에 완료됐다. 실제 full getter는 44개 화면·4,820개 노드·실제 Group 2개·main 24개·set 2개·instance 494개·variable 69개이며 정상 상위 검증과 순수 native 검증이 모두 통과했다. [grouping-qa.json](../../apps/little-hands/design/grouping-qa.json)은 원래 source capture를 바꾸지 않은 portable overlay와 실제 후보의 대응을 기록한다. R7 대비 제품 leaf 3,171개의 bbox 차이 0, Frame clip 550개·기존 reaction node 314개의 semantic 연결 보존을 확인했다.

R8 같은 패킷 재실행은 15.502초에 같은 페이지·전체 4,820개 ID를 유지했고 opacity override는 0개였다. 별도 R7 실제 opacity 0.9 override는 같은 패킷에서 보존됐고 숫자 1로 복원한 뒤 정상 verifier가 통과했다. explicit opacity flag는 보관된 R7에 남으며 새 R8 clean 상태와 구분한다. 복사본 sizing 실험의 다섯 label·크기·main·parent는 복원하고 임시 wrapper를 제거했다.

R8 두 set의 실제 Component Configuration에서 description·link가 모두 비어 있음을 확인했다. 정의는 TEXT와 각 12개의 Visual이며 control_styles 선언과 일치한다. 미선언 생성 금지의 근거이지 optional BOOLEAN/SWAP 양성 생성의 근거가 아니다.

실제 Figma history에서 R8의 named saved version과 공식 UI의 로컬 .fig backup 2,767,296바이트를 확인했다. 이는 UI 관찰·로컬 보존이며 독립적인 원격 저장소의 암호학적 검증은 아니다. 원시 native ID·file key·개인 경로·인증값은 공개하지 않는다.

## 실제 summary·진단과 조건별 관찰

R7 실제 summary는 4,818개 노드의 width/height가 이전 full과 불일치 0개였고 무거운 필드는 없었다. 실제 Figma 진단의 profile summary·complete false·node ID/field/omission 목록은 읽기와 정확히 일치했다. 후속 full 읽기 뒤 진단은 최신 full로 교체됐으며 node·variable·collection 내용이 원본 full과 일치했다. no-read 내보내기도 실제 패널에서 미관찰 상태를 표시했다. summary를 일반 graph import `--apply`·pair에 사용하면 거절됐고 출력 없음·graph bytes 보존을 확인했다.

실제 legacy Figma 진단의 보이는 Markdown·fenced JSON·다운로드 파일 내용과 0.27 버전이 일치했다. 후속 신뢰된 클릭의 clipboard 2,464자와 모든 표시·파일의 일치로 RD-09-AC-01을 확인했다. 초기 키보드 복사 실패 근거는 보존한다. 코드 fixture·로컬 서버/HTTP fault 실행·실제 패널 조작의 구별은 각 행에 적었다.

RD-08-AC-04는 독립 검토에서 terminal duplicate gap을 찾고 `1e64ada`에 제품 변경 전 고정한 7개 검사에서 예상 assertion 실패 5개를 확인한 뒤 수정했다. 같은 고정 검사 7개와 관련 control/RD-07/RD-08/lifecycle 52개가 통과했고 독립 검토를 마쳤다. result는 ID·scope·크기를 검사하고 raw readback 문자열 바이트까지 포함한 canonical payload SHA와 private terminal receipt를 비교한다. 일치한 과거 결과에는 저장소 변경 없이 원래 ACK를 반환하고 fingerprint 없는 legacy·서버 terminal·상충 결과는 거절한다.

주 세션은 새 소스 모듈로 control 서버를 재시작하고 workspace·plugin을 재개한 뒤 실제 Figma full 4,818개 노드·variable 69개 읽기를 성공시켰다. 저장된 fingerprint를 확인한 그 결과를 인증 HTTP `/control/result`로 정확히 재전송하면 원래 ACK와 200을 반환했고 raw JSON 끝에 newline을 추가하면 409로 거절했다. 두 호출에서 receipt/readback/uncertainty hash·mtime이 보존됐고 native 쓰기가 없었다. 보호된 terminal-actual-http-evidence.json·terminal-runtime-native-read.json이 근거이며 원시 경로·ID·인증값은 공개하지 않는다. 이 범위의 통과와 수정 후 전체 suite·이후 CI는 구분한다.

## 고정 검사와 native 실행의 구분

[finalize_historical_restore.py](../../tests/finalize_historical_restore.py)의 4개 검사는 실제 CLI에서 인증된 retained row·bundle의 A→B→A 복원, 입력 currentness·root·record·expected revision guard와 미보존 번들의 권한 배제를 검증한다. `06a40a1`의 canonical 임시 root 보정 뒤 기본 환경에서 4개 통과를 담당 작업자와 주 세션이 보고했다. 이 검사는 로컬 준비·게시 계약이며 Figma 관찰이 아니다.

[finalize_native_build_reads.cjs](../../tests/finalize_native_build_reads.cjs)의 고정 5개 검사는 normal `makeDraft`와 reader의 getter 작업량, annotation batch indexing, 독립 read의 최신 값 및 실패 보존을 검사한다. 주 세션은 5개 통과를 보고했다. API 형태의 fixture이며 실제 44개 화면 생성 시간이나 native 인수 통과를 증명하지 않는다.

이전 44개 Frame 생성 실패·rollback과 uncertainty reconcile는 과거 실패 근거로 남긴다. 후속 R7 생성은 ok로 완료됐으며 실제 full getter 검토·동일 패킷 재실행·최종 discovery 결과를 위에 연결했다. 이전의 “생성 실행 중” 상태는 현재 결과가 아니다. 실패 복구의 모든 lifecycle 조건까지 닫았다는 의미는 아니다.

## 회귀·출시 경계

기존 회귀 계획은 [plan.md](../../specs/regression-program/plan.md), [cases.json](../../specs/regression-program/cases.json)를 따른다. 61개 legacy case의 전체 조건·입력 조합·웹/Figma 증거를 이 RD 표나 새 앱 하나로 닫지 않는다. inventory의 complete-case 판정과 실제 증거가 없는 범위는 미검증이다.

0.27 manifest 동기화·생성 패널 재빌드·CHANGELOG·패치 Wiki·commit 후 `python3 tools/patch_knowledge.py verify --ref HEAD`·푸시 결과는 주 세션의 별도 최종 실행 범위다. [integration.md](../../docs/llm-wiki/integration.md)의 기록 검사 통과는 browser/native 수용이나 운영 배포 증거가 아니다. 작성자는 commit·push·배포를 수행하지 않았다.

45 AC는 각 행의 명시 범위에서 통과했다. 이는 45 REQ의 모든 양성 기능이나 전체 제품·출시 인수를 뜻하지 않는다. RD-01 optional BOOLEAN/INSTANCE_SWAP 생성은 NF-01의 후속 제안이며 현재 지원으로 표시하지 않는다. 사람의 창작 품질·production admission, 물리 기기, 공개 DNS/TLS, 61개 legacy 전체 coverage, 실제 chat 첨부 전달은 아직 확인하지 않았다. 원본 앱의 영속 Graph SSOT도 연결하지 않았으며 임시 3색 실험은 복원했다.

이 표는 출시 전 소스의 검증 스냅샷이다. Codex 설치 0.26.3과 실제 native 0.27 후보를 구분한다. 최종 clean package 전체 검사·push 이후 CI·release·설치 검증은 주 세션의 다음 실행이며 미래 성공을 주장하지 않는다. 최종 소스와 실제 설치 영수증의 기준은 [패치 Wiki](../llm-wiki/README.md)와 [통합 절차](../llm-wiki/integration.md)의 해당 full-SHA release 기록이다. 이후 설치 상태를 이 스냅샷의 버전에서 추정하지 않는다.

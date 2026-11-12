# RD-05 설계서 · 입력 사진·글꼴·CSS 자산 목록

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/input_effect.py](../../../tools/input_effect.py) | `html_channel, project, freshness` |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `prepare와 task_surface의 새 전달 지점 후보` |
| [panel-ui/src/Workspace.jsx](../../../panel-ui/src/Workspace.jsx) | `prepared task 상세의 읽기 전용 disclosure 후보` |
| [panel-ui/src/ImportPanel.jsx](../../../panel-ui/src/ImportPanel.jsx) | `기존 선택 파일 UX. 자동으로 이 패널을 재사용하지 않음` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

제안하는 task 부가 참조는 `input_record:{artifact,sha256}`다. 실제 원시 record는 private task artifact에 유지하고 UI에는 안전한 상대 경로·종류·상태·출처와 truncated digest를 projection한다. 이 필드와 UI 소비자는 아직 없다.

첫 구현 전에 producer에서 해당 task까지의 전달 경로를 확정한다. 권장 범위는 `figma_workspace.prepare`가 선택적 input record를 받고 검증된 artifact로 복사하는 방식이다. 실제 code path와 authority를 확인하기 전 새 CLI flag 이름을 확정하지 않는다.

기존 status enum과 hash를 재사용한다. 미지원 확장자·파싱 불가·외부 확인 불가를 present로 바꾸지 않는다.

## 구현 결정

데이터 원본은 input-effect record 하나다. UI가 HTML/CSS를 다시 파싱하지 않는다. freshness 결과와 목록의 source digest를 같은 task revision에 묶는다.

현재 Workspace의 작업 상세 안에 자산 disclosure를 추가한다. 첫 화면은 문제 있는 항목과 종류별 수를 보여주고 검색 시 전체 목록을 읽는다. 목록 count는 파일 준비 상태이며 실제 렌더 성공률이 아니다. path와 파일명은 text로 렌더하고 HTML로 삽입하지 않는다.

민감한 외부 URL query·fragment와 개인 절대 경로를 UI 요약에서 제거한다. 원시 record는 기존 private 저장 규칙을 따른다. 긴 목록은 제한된 행을 먼저 보여주되 전체 수와 나머지 보기 동작을 명시한다.

## 호환성·이관·복구

input record가 없는 task에는 목록 없음 상태를 표시한다. 빈 목록을 모든 파일이 정상이라는 의미로 쓰지 않는다. 기존 record v1/v2는 현재 v3로 재준비하도록 안내하고 오래된 결과를 UI에서 임의 정상화하지 않는다. 기능 제거 시 private 원본과 prepared task의 실행 권한에 영향을 주지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.



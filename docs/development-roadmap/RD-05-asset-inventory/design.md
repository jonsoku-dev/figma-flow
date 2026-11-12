# RD-05 설계서 · 입력 사진·글꼴·CSS 자산 목록

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/input_effect.py](../../../tools/input_effect.py) | `html_channel, project, freshness` |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `prepare와 task_surface의 새 전달 지점 후보` |
| [panel-ui/src/Workspace.jsx](../../../panel-ui/src/Workspace.jsx) | `prepared task 상세의 읽기 전용 disclosure 후보` |
| [panel-ui/src/ImportPanel.jsx](../../../panel-ui/src/ImportPanel.jsx) | `기존 선택 파일 UX. 자동으로 이 패널을 재사용하지 않음` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

확정 경로: input_effect.project가 html_channel로 HTML 자산을 모으고, freshness와 write_record를 거친 뒤 figma_workspace.prepare가 검증된 record만 private task artifact로 복사한다. ImportPanel은 이 목록의 소비자가 아니다.

CLI `prepare --input-record <JSON> --input-root <root>`는 Python `prepare(..., input_record=..., input_root=...)`로 전달한다. `--input-root`에는 input record가 필요하다. `--depends-on <JSON>`은 같은 prepare의 독립적인 명시적 dependency 입력이다. input-effect에 별도 argparse를 만들지 않는다.

record는 현재 `RESULT_SCHEMA`를 따르며 task에는 `input_record:{artifact:"input-record.json",sha256}`를 저장한다. record는 1 MB 이내이고 root를 준 경우 `sources`의 상대 path와 SHA-256을 검증한다. 준비 전후 실제 source hash가 current여야 한다. 원본 root는 private task에만 남고 공개 metadata에서 제거한다. root 없이 record만 준비한 경우 현재성은 `unverified`다.

`summarize_input_record`는 `input_summary`의 `ref`, `kind`, `status`, `source`, 짧은 `digest`만 투영한다. 상태는 `present`, `404`, `rejected`, `external-unverified`를 보존한다. 같은 로컬 path·kind·status의 자산은 canonical identity로 합치고 여러 CSS 출처는 `sources`로 보존한다.

## 구현 결정

input-effect record 하나를 사용하며 UI는 HTML이나 CSS를 다시 파싱하지 않는다. private artifact의 실제 bytes와 pin을 조회 때 다시 확인한다. replay는 저장한 input record와 root를 다시 admission에 넣으며 stale source를 기존 성공으로 재사용하지 않는다. root가 있던 기존 task를 교체할 때 record나 root를 누락하면 거절한다.

`task_input_freshness`와 scoped history 응답의 `inputFreshness`는 task key와 exact revision에 current, stale, unverified를 연결한다. 변경 경로는 안전한 참조로만 보낸다. `Workspace.jsx`의 `AssetDisclosure`는 종류별 수, 문제 우선 정렬, 상태·종류·검색 필터와 더 보기로 `assetInventory`를 표시한다. 파일 준비 상태는 브라우저 요청 성공이나 실제 렌더 성공을 뜻하지 않는다.

외부 URL의 credentials·query·fragment와 개인 절대 경로를 요약에서 제거한다. path는 React text로 렌더한다. raw record와 source root는 private 저장 규칙을 따른다.

## 호환성·이관·복구

input record가 없는 task에는 목록 없음 상태를 표시한다. 빈 목록을 모든 파일이 정상이라는 의미로 쓰지 않는다. 기존 record v1/v2는 현재 v3로 재준비하도록 안내하고 오래된 결과를 UI에서 임의 정상화하지 않는다. 기능 제거 시 private 원본과 prepared task의 실행 권한에 영향을 주지 않는다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.



# RD-03 설계서 · 작업 간 의존성과 영향 시각화

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `prepare, publish, replay, retire` |
| [figma-bridge/workspace_host.js](../../../figma-bridge/workspace_host.js) | `안전한 task projection` |
| [panel-ui/src/Workspace.jsx](../../../panel-ui/src/Workspace.jsx) | `작업 목록·이력` |
| [tools/figma_control.py](../../../tools/figma_control.py) | `실행 식별·scope 경계` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 현재 데이터와 인터페이스

`figma_workspace prepare --depends-on <JSON>`과 Python `prepare(..., depends_on=...)`가 명시적 `uses-output` edge를 받는다.

```json
{"depends_on":[{"task_key":"review-a","revision":"exact-revision","relation":"uses-output","artifact":"code.js","artifact_sha256":"64-hex-digest"}]}
```

`normalize_task_dependencies`는 현재 task 또는 검증된 history의 exact revision과 등록된 `code.js`, `ui.html`, `manifest.json`의 digest를 대조한다. 임의 readback 이름, 경로, self edge, 중복 edge와 cycle은 거절한다. 같은 프로젝트나 단계 순서는 dependency를 만들지 않는다. 원본은 catalogue이고 UI adjacency는 읽기 전용 projection이다.

## 구현 결정

prepare, publish, replay는 검증된 artifact와 source pin을 보존한다. retire된 선행 작업의 exact artifact가 trusted history에 남아 있으면 역사 edge를 유지한다. 선행 revision 변경·retire·unavailable은 `dependencyFreshness`가 구분하며 자동 재준비나 자동 실행을 하지 않는다.

`Workspace.jsx`의 `DependencyText`는 `dependencyView` 결과를 SVG와 같은 내용의 텍스트 목록으로 보여준다. 선택한 task의 한 단계 선행·후속, 고정 revision과 현재 revision, artifact 이름과 digest를 표시한다. 의미 requirement graph나 RD-08의 operation journal을 이 graph로 대체하지 않는다. UI 관계 표시는 native mutation 권한을 만들지 않는다.

## 호환성·이관·복구

의존성 없는 기존 catalogue는 빈 목록으로 읽는다. 기존 task revision을 몰래 변경하지 않는다. 새 edge 추가는 새 준비 revision을 만들며 기존 실행 영수증을 보존한다. 선행 작업 retire 후에도 pinned artifact가 보존되면 역사 edge를 읽을 수 있어야 한다. 시각화를 끄더라도 catalogue의 명시적 관계는 보존한다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.



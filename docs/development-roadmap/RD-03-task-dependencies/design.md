# RD-03 설계서 · 작업 간 의존성과 영향 시각화

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 소유 코드와 호출 경로

| 현재 파일 | 관련 심볼·책임 |
| --- | --- |
| [tools/figma_workspace.py](../../../tools/figma_workspace.py) | `prepare, publish, replay, retire` |
| [figma-bridge/workspace_host.js](../../../figma-bridge/workspace_host.js) | `안전한 task projection` |
| [panel-ui/src/Workspace.jsx](../../../panel-ui/src/Workspace.jsx) | `작업 목록·이력` |
| [tools/figma_control.py](../../../tools/figma_control.py) | `실행 식별·scope 경계` |

해당 모듈의 작성자는 한 명으로 정한다. 다른 항목이 같은 파일을 쓰면 먼저 완료하거나 소유권을 넘긴 뒤 통합한다.

## 데이터와 인터페이스 제안

제안 필드이며 현재 CLI에는 존재하지 않는다.

```json
{"depends_on":[{"task_key":"review-a","revision":"exact-revision","relation":"uses-output","artifact":"readback.json","artifact_sha256":"64-hex-digest"}]}
```

첫 relation은 `uses-output`만 지원한다. artifact는 선행 revision의 서명된 artifact 목록에 등록된 상대 이름이다. 절대 경로·..·symlink·등록되지 않은 이름은 거절한다. 같은 바이트를 가진 파일이 여럿이어도 이름과 hash를 함께 고정한다. 같은 프로젝트라는 관계는 dependency로 저장하지 않는다. 원본 관계 inventory는 workspace catalogue 하나로 유지하고 UI adjacency는 projection이다. 의미 requirement graph를 task 실행 graph로 대체하지 않는다.

## 구현 결정

prepare 경계에서 artifact 존재와 source pins를 확인한 뒤 exact revision edge를 저장한다. publish는 전체 task 집합에서 DAG를 검사한다. JSON 입력과 catalogue 서명에 dependency를 포함하고 UI에는 안전한 key/revision/relation과 artifact의 상대 이름·digest를 전달한다. 상세에서 exact artifact identity와 pinned hash를 볼 수 있다.

처음에는 SVG와 HTML 목록을 함께 사용한다. node 수가 많으면 선택 task의 한 단계 선행·후속만 펼친다. 선은 명시적 dependency에만 그리며 step 위치나 task kind에서 추론하지 않는다. 연결선 애니메이션은 선택·변경에만 한정하고 reduced motion에서 제거한다.

RD-08의 영속 operation ID와 task dependency key는 별개다. 실행의 request/result 관계와 제작 산출물의 uses-output 관계를 다른 레이블로 표현한다.

## 호환성·이관·복구

의존성 없는 기존 catalogue는 빈 목록으로 읽는다. 기존 task revision을 몰래 변경하지 않는다. 새 edge 추가는 새 준비 revision을 만들며 기존 실행 영수증을 보존한다. 선행 작업 retire 후에도 pinned artifact가 보존되면 역사 edge를 읽을 수 있어야 한다. 시각화를 끄더라도 catalogue의 명시적 관계는 보존한다.

## 오류와 개인정보

입력 validation과 현재 scope·revision·source pin은 기존 경계에서 확인한다. 실패는 기존 값을 보존하고 원인을 구분해 반환한다. 원시 readback, 개인 텍스트, control/pairing 값과 설치 경로는 공유 Wiki나 UI 요약에 포함하지 않는다.



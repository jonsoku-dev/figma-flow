# 작업 이력과 실행 흐름

원본 요청은 [request.md](request.md), 관계 inventory는 [graph.json](graph.json), 화면 설명은 [screen-spec.md](screen-spec.md)다.

## 요구사항

- `REQ-ACTIVITY-01` — 현재 task revision별 마지막 관측 상태를 차트와 정확한 수로 보여준다.
- `REQ-ACTIVITY-02` — 실제 dispatch에서 만든 실행 ID로 같은 task·revision의 요청·결과·검증을 연결한다.
- `REQ-ACTIVITY-03` — 옛 이력과 현재 실행을 구분하고 작업별 이력·시간순 원본을 찾을 수 있게 한다.
- `REQ-ACTIVITY-04` — 기존 디자인 시스템 안에서 제한된 애니메이션, 키보드 탐색, 좁은 폭, 테마와 세 언어를 지원한다.

## 인수 조건

- `AC-ACTIVITY-01` — pending/requested/running/finished/readback/baseline/verified/failed의 수가 현재 task·revision의 마지막 관측과 일치한다. chat·download·이전 revision·삭제 task는 현재 완료 수에 포함하지 않는다.
- `AC-ACTIVITY-02` — 직접 UI와 자동 제어의 실제 실행마다 새 ID가 생성된다. 같은 실행의 요청·결과는 같은 ID를 사용하며 task·revision이 다르면 같은 저장 ID로 합치지 않는다. 외부가 보낸 ID를 권한으로 사용하지 않는다.
- `AC-ACTIVITY-03` — 실행 ID 없는 옛 이력은 연결되지 않은 시간순 자료로 표시한다. 기존 이력 요약과 실패를 지우지 않고 최근80건의 제한과 file-scoped 저장을 유지한다.
- `AC-ACTIVITY-04` — 작업별 필터와 목록의 이력 링크가 해당 작업의 현재·옛 이력을 열고 초점을 보낸다. 조회·확장·필터는 native mutation을 요청하지 않는다.
- `AC-ACTIVITY-05` — 실제 브라우저의320/560/840px와 light/dark에서 가로 넘침 없이 읽을 수 있고 키보드로 필터·summary를 조작한다. 한국어·영어·일본어 copy의 placeholder가 일치한다.
- `AC-ACTIVITY-06` — 짧은 상태·펼침 feedback만 사용한다. reduced-motion CSS에서 해당 효과를 제거하며 상시 loop·추가 animation/chart dependency를 넣지 않는다. OS 설정 전환의 실제 관찰 여부는 따로 기록한다.

## 의미와 권한 경계

실행 완료, 실제 읽기 완료, 읽기 검증 완료는 다른 상태다. 차트는 전체 제품 인수 완료율이 아니다. 이력은 clientStorage의 관측 요약이며 Python control journal의 권한·현재 native 값·클라우드 저장을 인증하지 않는다. 시간순·같은 project·task kind에서 작업 간 인과관계를 추정하지 않는다.

기존80건 저장 형식을 유지하고 실행 ID를 선택적으로 보존한다. 잘못된 ID는 제거하되 안전한 기존 event 요약은 유지한다. download에는 앞선 실행 ID를 물려주지 않는다. private readback이나 control 값은 새 UI·history에 복사하지 않는다.

검사·브라우저·실제 설치 Figma 관찰은 [검증 범위](../../docs/llm-wiki/verification.md)에 별도로 기록한다. graph 노드의 등록만으로 실행 성공을 주장하지 않는다.

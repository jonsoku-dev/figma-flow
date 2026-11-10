# 오늘의 복습 카드 화면 기획서

[원문 기획](brief.md)과 [선택된 초안](draft.json)의 화면 ID와 기존 전환 관계를 유지한다. 브라우저에서 학습 방법을 다루는 예시 카드 네 장을 제공한다. 이번 예제에서 ‘오늘 분량’은 한 번 연 페이지의 카드 묶음으로 정했다. 새로고침하면 진행을 처음부터 시작한다.

## SCR-CARDS-LIST · 오늘의 카드

목록에서 남은 카드와 완료 수를 보여 준다. 제목 검색어를 입력하면 일치하는 미완료 카드만 남는다. 검색 결과가 없을 때는 검색어를 지울 수 있다. 모든 카드를 완료했을 때는 완료 안내를 보여 준다. 검색 결과가 없는 상태와 분량을 마친 상태는 구분한다.

| 원문 요구사항 | 동작·상태 | 결정 및 검증 위치 |
|---|---|---|
| REQ-CARDS-LIST | STATE-CARDS-LIST | [목록 규칙](specs/list.md) · tests/list.test.cjs |
| REQ-CARDS-QUESTION | ACT-CARDS-OPEN → SCR-CARDS-REVIEW / STATE-CARDS-QUESTION | [질문 규칙](specs/question.md) · tests/question.test.cjs |
| REQ-CARDS-SEARCH | ACT-CARDS-SEARCH → 목록 또는 STATE-CARDS-EMPTY-SEARCH | [검색 규칙](specs/search.md) · tests/search.test.cjs |
| REQ-CARDS-FINISH | STATE-CARDS-DONE | [분량 완료 규칙](specs/finish.md) · tests/finish.test.cjs |

## SCR-CARDS-REVIEW · 질문과 정답

카드를 열면 질문과 ‘정답 보기’가 나타난다. 정답 공개 전에는 복습 결과를 선택할 수 없다. 공개 후에는 ‘다시 연습’과 ‘복습 완료’를 선택할 수 있다. 목록으로 돌아가기는 완료 기록을 바꾸지 않는다.

| 요구사항 | 동작·상태 | 결정 및 검증 위치 |
|---|---|---|
| REQ-CARDS-ANSWER | ACT-CARDS-REVEAL → STATE-CARDS-ANSWER | [정답 공개 규칙](specs/answer.md) · tests/answer.test.cjs |
| REQ-CARDS-RETRY | ACT-CARDS-RETRY → STATE-CARDS-QUESTION | [다시 연습 규칙](specs/retry.md) · tests/retry.test.cjs |
| REQ-CARDS-COMPLETE | ACT-CARDS-COMPLETE → SCR-CARDS-LIST / 남은 목록 또는 완료 상태 | [카드 완료 규칙](specs/complete.md) · tests/complete.test.cjs |

버튼은 기본 키보드 동작을 지원한다. 카드를 열면 제목, 정답을 공개하면 정답 영역, 다시 연습하면 질문으로 포커스를 옮긴다. 목록과 복습 화면의 실제 구성은 [앱](app/index.html)에서 확인할 수 있다.

## 변경 시 기준

각 규칙의 상세 동작은 위 표가 가리키는 개별 명세에서 관리한다. 화면 연결과 코드·검사 관계는 [그래프](graph.json), 테스트 파일 선택은 [테스트 매핑](test-mapping.json)에서 확인한다. ACC-CARDS-*의 결과는 해당 TEST-CARDS-* 증거로 추적한다. 개별 명세가 바뀌면 기준 매니페스트로 영향을 먼저 검사한다.

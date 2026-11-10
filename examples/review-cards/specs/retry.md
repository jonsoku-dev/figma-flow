# 다시 연습 · 다음 미완료 카드

REQ-CARDS-RETRY / ACT-CARDS-RETRY / ACC-CARDS-RETRY. 정답을 본 상태에서 ‘다시 연습’을 선택하면 현재 카드를 완료 처리하지 않는다. 덱의 원래 순서에서 **다음 미완료 카드**를 찾아 정답이 숨겨진 질문으로 이동한다. 마지막 카드를 지나면 처음부터 찾고, 남은 카드가 한 장이면 같은 질문을 다시 보여 준다. 검색어, 완료 수와 덱 순서는 보존한다. 정답 공개 전이나 목록에서의 호출은 상태를 바꾸지 않는다.

화면은 SCR-CARDS-REVIEW를 유지하고 목적 상태는 STATE-CARDS-QUESTION이다. app/rules/retry.js가 이 규칙을 구현하고 tests/retry.test.cjs가 검증한다. 검색·완료 동작은 각각의 규칙 명세에서 관리한다.

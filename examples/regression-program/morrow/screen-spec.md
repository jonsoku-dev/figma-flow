# Morrow Market 화면 명세

이 문서는 카탈로그의 화면 ID를 풀어 쓴 것이다. 그래프가 관계의 기준이고, 이 파일은 Figma 증거가 아니다.

## SCR-MORROW-01 이번 주의 식탁

- 경로: `/`
- 요구: `REQ-MORROW-01` 주간 식탁 이야기를 연다.
- 주 행동: `ACT-MORROW-01` 컬렉션 보기
- 인수: `AC-MORROW-01` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-02 주간 컬렉션

- 경로: `/collections/:slug`
- 요구: `REQ-MORROW-02` 컬렉션 안의 상품으로 이동한다.
- 주 행동: `ACT-MORROW-02` 상품 보기
- 인수: `AC-MORROW-02` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-03 상품 찾기

- 경로: `/search`
- 요구: `REQ-MORROW-03` 이름과 재료로 상품을 찾는다.
- 주 행동: `ACT-MORROW-03` 상품 보기
- 인수: `AC-MORROW-03` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-04 식탁 상품

- 경로: `/products/:productId`
- 요구: `REQ-MORROW-04` 가격과 재고를 보여 주고 담는다.
- 주 행동: `ACT-MORROW-04` 장바구니에 담기
- 인수: `AC-MORROW-04` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-05 나란히 비교

- 경로: `/compare`
- 요구: `REQ-MORROW-05` 두 상품의 가격과 재고를 나란히 둔다.
- 주 행동: `ACT-MORROW-05` 장바구니로 이동
- 인수: `AC-MORROW-05` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-06 보관한 상품

- 경로: `/saved`
- 요구: `REQ-MORROW-06` 새로고침 뒤에도 보관한 상품을 유지한다.
- 주 행동: `ACT-MORROW-06` 상품 보기
- 인수: `AC-MORROW-06` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-07 장바구니

- 경로: `/cart`
- 요구: `REQ-MORROW-07` 담은 상품과 수량을 확인한다.
- 주 행동: `ACT-MORROW-07` 주문 시작
- 인수: `AC-MORROW-07` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-08 주문자

- 경로: `/checkout/contact`
- 요구: `REQ-MORROW-08` 주문자 이름을 받는다. 결제는 없다.
- 주 행동: `ACT-MORROW-08` 배송으로 이동
- 인수: `AC-MORROW-08` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-09 배송

- 경로: `/checkout/delivery`
- 요구: `REQ-MORROW-09` 배송 메모를 받고 이전 단계로 돌아갈 수 있다.
- 주 행동: `ACT-MORROW-09` 확인으로 이동
- 인수: `AC-MORROW-09` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-10 주문 확인

- 경로: `/checkout/review`
- 요구: `REQ-MORROW-10` 재고나 가격이 바뀌면 주문을 늘리지 않는다.
- 주 행동: `ACT-MORROW-10` 주문 접수
- 인수: `AC-MORROW-10` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-11 주문 완료

- 경로: `/orders/complete/:orderId`
- 요구: `REQ-MORROW-11` 한 번 접수된 주문 번호를 보여 준다.
- 주 행동: `ACT-MORROW-11` 주문 상세
- 인수: `AC-MORROW-11` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-12 주문 목록

- 경로: `/orders`
- 요구: `REQ-MORROW-12` 접수한 주문을 다시 연다.
- 주 행동: `ACT-MORROW-12` 주문 상세
- 인수: `AC-MORROW-12` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-13 주문 상세

- 경로: `/orders/:orderId`
- 요구: `REQ-MORROW-13` 주문 내용을 확인하고 반품으로 이동한다.
- 주 행동: `ACT-MORROW-13` 반품 신청
- 인수: `AC-MORROW-13` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-MORROW-14 반품 신청

- 경로: `/returns/new/:orderId`
- 요구: `REQ-MORROW-14` 반품 실패 뒤 입력한 사유를 유지한다.
- 주 행동: `ACT-MORROW-14` 반품 제출
- 인수: `AC-MORROW-14` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## 핵심 흐름

- `TC-F03` 주문 단계와 재고 충돌: SCR-MORROW-04, SCR-MORROW-07, SCR-MORROW-08, SCR-MORROW-09, SCR-MORROW-10, SCR-MORROW-11
- `TC-F04` 저장 목록과 반품: SCR-MORROW-06, SCR-MORROW-13, SCR-MORROW-14

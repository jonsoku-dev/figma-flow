# Paper Room 화면 명세

이 문서는 카탈로그의 화면 ID를 풀어 쓴 것이다. 그래프가 관계의 기준이고, 이 파일은 Figma 증거가 아니다.

## SCR-PAPER-01 읽는 사람의 첫 화면

- 경로: `/`
- 요구: `REQ-PAPER-01` 발행된 글의 첫 문단만 보여 준다.
- 주 행동: `ACT-PAPER-01` 글 읽기
- 인수: `AC-PAPER-01` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-02 글 찾기

- 경로: `/search`
- 요구: `REQ-PAPER-02` 제목과 본문에서 글을 찾는다.
- 주 행동: `ACT-PAPER-02` 글 읽기
- 인수: `AC-PAPER-02` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-03 글

- 경로: `/articles/:slug`
- 요구: `REQ-PAPER-03` 긴 글을 좁은 폭으로 읽는다.
- 주 행동: `ACT-PAPER-03` 보관
- 인수: `AC-PAPER-03` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-04 책상 모음

- 경로: `/collections/:collectionId`
- 요구: `REQ-PAPER-04` 모음에 들어 있는 글을 연다.
- 주 행동: `ACT-PAPER-04` 글 읽기
- 인수: `AC-PAPER-04` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-05 보관한 글

- 경로: `/saved`
- 요구: `REQ-PAPER-05` 보관한 글을 다시 연다.
- 주 행동: `ACT-PAPER-05` 글 읽기
- 인수: `AC-PAPER-05` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-06 작업실

- 경로: `/studio`
- 요구: `REQ-PAPER-06` 작성자와 편집자의 작업실이다.
- 주 행동: `ACT-PAPER-06` 초고 목록
- 인수: `AC-PAPER-06` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-07 초고 목록

- 경로: `/studio/articles`
- 요구: `REQ-PAPER-07` 초고와 검토 상태를 보여 준다.
- 주 행동: `ACT-PAPER-07` 새 글
- 인수: `AC-PAPER-07` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-08 새 글

- 경로: `/studio/articles/new`
- 요구: `REQ-PAPER-08` 새 초고를 만든다.
- 주 행동: `ACT-PAPER-08` 편집 시작
- 인수: `AC-PAPER-08` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-09 글 편집

- 경로: `/studio/articles/:articleId/edit`
- 요구: `REQ-PAPER-09` 자동 저장이 실패해도 본문을 유지한다.
- 주 행동: `ACT-PAPER-09` 검토 요청
- 인수: `AC-PAPER-09` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-10 검토 목록

- 경로: `/studio/reviews`
- 요구: `REQ-PAPER-10` 검토 대기 글을 연다.
- 주 행동: `ACT-PAPER-10` 검토 열기
- 인수: `AC-PAPER-10` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-11 검토 상세

- 경로: `/studio/reviews/:reviewId`
- 요구: `REQ-PAPER-11` 편집자가 반려하거나 가상 발행한다. 공개 발행은 없다.
- 주 행동: `ACT-PAPER-11` 가상 발행
- 인수: `AC-PAPER-11` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-PAPER-12 발행 달력

- 경로: `/studio/calendar`
- 요구: `REQ-PAPER-12` 가상 발행된 글만 달력에 올린다.
- 주 행동: `ACT-PAPER-12` 첫 화면으로
- 인수: `AC-PAPER-12` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## 핵심 흐름

- `TC-F05` 작성·자동 저장·검토: SCR-PAPER-08, SCR-PAPER-09, SCR-PAPER-10
- `TC-F06` 역할별 검토·발행: SCR-PAPER-11, SCR-PAPER-01, SCR-PAPER-12

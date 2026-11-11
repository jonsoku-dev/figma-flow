# Atlas Workspace 화면 명세

이 문서는 카탈로그의 화면 ID를 풀어 쓴 것이다. 그래프가 관계의 기준이고, 이 파일은 Figma 증거가 아니다.

## SCR-ATLAS-01 Atlas 로그인

- 경로: `/sign-in`
- 요구: `REQ-ATLAS-01` 모의 역할로 작업 공간에 들어간다.
- 주 행동: `ACT-ATLAS-01` 작업 공간 열기
- 인수: `AC-ATLAS-01` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-02 작업 공간 선택

- 경로: `/workspaces`
- 요구: `REQ-ATLAS-02` Northwind 작업 공간을 고른다.
- 주 행동: `ACT-ATLAS-02` Northwind 열기
- 인수: `AC-ATLAS-02` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-03 오늘의 검토

- 경로: `/dashboard`
- 요구: `REQ-ATLAS-03` 오늘 처리할 승인과 할 일을 밀도 높게 보여 준다.
- 주 행동: `ACT-ATLAS-03` 승인 대기 열기
- 인수: `AC-ATLAS-03` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-04 프로젝트 목록

- 경로: `/projects`
- 요구: `REQ-ATLAS-04` 프로젝트 표를 정렬하고 좁힌다.
- 주 행동: `ACT-ATLAS-04` 프로젝트 열기
- 인수: `AC-ATLAS-04` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-05 프로젝트 상세

- 경로: `/projects/:projectId`
- 요구: `REQ-ATLAS-05` 프로젝트의 할 일 수를 보여 준다.
- 주 행동: `ACT-ATLAS-05` 보드로 이동
- 인수: `AC-ATLAS-05` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-06 작업 보드

- 경로: `/projects/:projectId/board`
- 요구: `REQ-ATLAS-06` 칸반이 아니라 상태 열로 할 일을 연다.
- 주 행동: `ACT-ATLAS-06` 할 일 열기
- 인수: `AC-ATLAS-06` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-07 할 일 상세

- 경로: `/tasks/:taskId`
- 요구: `REQ-ATLAS-07` 저장 실패 뒤에도 초안을 유지한다.
- 주 행동: `ACT-ATLAS-07` 저장
- 인수: `AC-ATLAS-07` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-08 승인 목록

- 경로: `/approvals`
- 요구: `REQ-ATLAS-08` 대기 중인 승인 요청을 보여 준다.
- 주 행동: `ACT-ATLAS-08` 요청 열기
- 인수: `AC-ATLAS-08` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-09 승인 상세

- 경로: `/approvals/:approvalId`
- 요구: `REQ-ATLAS-09` 검토자가 요청을 승인하고 구성원은 읽기 전용이다.
- 주 행동: `ACT-ATLAS-09` 승인
- 인수: `AC-ATLAS-09` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-10 구성원

- 경로: `/members`
- 요구: `REQ-ATLAS-10` 구성원과 현재 역할을 보여 준다.
- 주 행동: `ACT-ATLAS-10` 초대
- 인수: `AC-ATLAS-10` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-11 구성원 초대

- 경로: `/members/invite`
- 요구: `REQ-ATLAS-11` 초대 대상을 입력한다. 메일은 보내지 않는다.
- 주 행동: `ACT-ATLAS-11` 초대 보내기
- 인수: `AC-ATLAS-11` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-12 역할

- 경로: `/roles`
- 요구: `REQ-ATLAS-12` 관리자만 역할 목록을 연다.
- 주 행동: `ACT-ATLAS-12` 역할 열기
- 인수: `AC-ATLAS-12` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-13 역할 상세

- 경로: `/roles/:roleId`
- 요구: `REQ-ATLAS-13` 관리자가 구성원의 역할을 바꾼다.
- 주 행동: `ACT-ATLAS-13` 역할 저장
- 인수: `AC-ATLAS-13` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## SCR-ATLAS-14 작업 공간 설정

- 경로: `/settings`
- 요구: `REQ-ATLAS-14` 표시 밀도를 저장한다.
- 주 행동: `ACT-ATLAS-14` 표시 저장
- 인수: `AC-ATLAS-14` (TC-W01, 모델 검사 전 상태는 planned)
- 구현: `app/rules.js`

## 핵심 흐름

- `TC-F01` 할 일 저장과 복구: SCR-ATLAS-04, SCR-ATLAS-05, SCR-ATLAS-06, SCR-ATLAS-07
- `TC-F02` 승인과 역할 제한: SCR-ATLAS-08, SCR-ATLAS-09, SCR-ATLAS-13

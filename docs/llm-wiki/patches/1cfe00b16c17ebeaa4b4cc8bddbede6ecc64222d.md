<!-- patch-knowledge
{"commit":"1cfe00b16c17ebeaa4b4cc8bddbede6ecc64222d","diff_sha256":"104c6733156a5ce2abef9617ee191aafd50dfbcd50d75f21ee251a3868972c13","files":["specs/regression-program/cases.json","specs/regression-program/plan.md"],"parents":["e179df281a870086582ad25cf649931af5a8eaa2"],"subject":"docs: preserve regression witnesses and scope new checks","tree":"74ebec9d6fbe23f4ca7b244d50af260b5f27d62f","versions":[{"path":"plugin.json","version":"0.26.2"},{"path":".codex-plugin/plugin.json","version":"0.26.2"}]}
-->

# docs: preserve regression witnesses and scope new checks

## 문제와 계기

회귀 프로그램의 일부 근거는 과거 `tools/input_effect.py`와 `tests/test_regression_program_inputs.py`의 내용을 가리켰다. v3 CSS 변경 뒤 현재 파일은 그 과거 witness와 바이트가 달라졌으므로 원래 실행이 무엇을 검증했는지 보존할 필요가 있었다. 동시에 2026-11-12에 실행한 추가 CSS·실제 이미지 첨부·복구·반복 사진 검증을 기존 61개 케이스 통과로 오인하지 않도록 범위를 분리해야 했다. 출처는 첫 부모 `e179df281a870086582ad25cf649931af5a8eaa2` 대비 두 스펙 파일의 실제 문서 diff다.
## 결과 동작

여섯 개의 과거 소스 witness 참조를 원래 Git 바이트에서 만든 내용 주소형 스냅샷으로 옮기고 각 참조에 `original_path`와 `source_revision`을 덧붙였다. 원본 183개 회귀 사례 참조는 유효한 상태로 보존된다. 새 보충 실행은 별도 `supplemental_validation`에 13개 hashed owner-local witness를 묶으며 전체 회귀 케이스 61개 상태는 모두 `unverified`로 유지한다. 케이스, 실행 조합과 인수 조건은 바꾸지 않았다.
## 변경 파일과 인터페이스

`specs/regression-program/cases.json`의 evidence 항목은 이동된 witness에 원본 경로·source revision을 남기고, 최상위 `supplemental_validation`은 날짜·검증 당시 코드 revision·범위·전체 케이스 상태·report hash를 기록한다. `specs/regression-program/plan.md`는 추가 확인한 범위와 남은 미검증 조건을 설명한다. 애플리케이션 코드, 실행기, 테스트 기준이나 신뢰 출처 설정은 수정하지 않았다. 런타임 `trusted_sources`는 기존 `tools/`, `figma-bridge/`, `library/` 범위 그대로이며 `specs/`를 실행 권한으로 추가하지 않는다.
## 설계 이유와 출처

과거 파일 경로가 현재 코드에 재사용되더라도 과거 바이트를 대체하지 않도록 원본 Git revision의 내용을 해시 이름으로 보존한다. 이는 예전 테스트 정의를 현재 수정된 소스에 대한 성공 근거로 오독하지 않게 한다. 보충 보고서는 0.26.2 후보 `e179df2` 상태에서 선택한 보조 시나리오만 고정하며 기존 3개 앱·16회 실행 전체를 완료했다고 주장하지 않는다. 근거는 `cases.json`의 기존 분포 및 스냅샷 참조와 `plan.md`의 2026-11-12 실행 범위다.
## 호환성·이관·복구

61개 기존 회귀 케이스의 내용·상태·실행 변형은 유지된다. 여섯 witness는 현재 working tree 경로 대신 content-addressed snapshot을 보며, 원래 Git source revision을 따로 기록하므로 역사 기준을 다시 식별할 수 있다. 실제 witness 파일과 supplemental report는 owner-local이며 배포 Wiki에 포함되지 않는다. 포크 사용자는 원본 Git 객체나 보충 witness를 받았다고 가정하지 말고 자신의 환경에서 미보유 범위를 재실행해야 한다. 새 근거를 추가해도 기존 부분 실패나 미검증 상태를 자동 승격하지 않는다.
## 검증과 미검증

기록 시점에 원래 184개 root evidence reference hash가 모두 일치했고, 기존 183개 case reference는 유효했다. 0.26.2 후보 코드에서 별도 실행한 실제 native 검증은 새 4-screen 생성에서 전체 4화면 verifier, 독립 56개 사진·8개 노트 확인, desktop/mobile handoff와 idempotent 재실행의 데이터 동등성을 관찰했다. Computer Use는 네 상태의 실행 프로토콜을 실제 관찰했다. 같은 패킷 충돌 가드는 Figma에서 오류와 기존 page ID를 보여주고 페이지 수를 13에서 13으로 유지했으며 기존 127개 노드와 사진 바이트를 보존했다. 1·6·14회 반복 이미지 구성은 전후 각 다섯 번 읽고 사진 SHA를 비교했다. 추가로 누락 명세 8개는 기존 페이지에 한정해 고쳤지만 오래된 14회 부분 생성 acknowledgement는 다시 쓰지 않았고 root/final completion metadata도 복원하지 않았다.

회귀 프로그램의 Python 1,072개 중 1,070 통과·2 skip, Node 224개 중 223 통과·1 skip, 데모 2개 통과는 해당 후보 소스에 대한 별도 전체 검사 기록이다. 이는 이 문서 전용 커밋에서 실행한 테스트가 아니며, 61개 케이스의 전체 완료를 뜻하지 않는다.
## 한계와 후속 개선

보고서와 witness 해시가 owner-local 파일의 존재·전달을 보장하지 않으며 포크에서 새로 확인한 증거도 아니다. 실기기 동작, 실제 UI를 통한 첨부 완료, 실제 브라우저 200% 확대, 클라우드 저장, 글꼴 바이너리 identity는 미검증이다. 추가 관찰은 통제된 보충 범위에 한정되고 전체 3개 앱/16-run 매트릭스는 계속 미완료다. 복구한 8개 명세가 이전 acknowledgement를 바꾸거나 검토 페이지의 최종 완료 메타데이터를 복원하지 않는다. 이 문서는 제품 코드를 수정하지 않으며 0.26.2 공개·전역 설치를 나타내지 않는다. 보고 마감 시 global install은 0.26.1이었다.
## 관련 기록

[직전 0.26.2 구현](e179df281a870086582ad25cf649931af5a8eaa2.md), [회귀 사례와 증거 연결](../../../specs/regression-program/cases.json), [2026-11-12 회귀 범위 기록](../../../specs/regression-program/plan.md), [예약/완료 메타데이터 경계](../decisions.md). owner-local report와 원본 witness는 공개 Wiki에 복사하지 않는다. 원문은 `git show 1cfe00b16c17ebeaa4b4cc8bddbede6ecc64222d`와 페이지 상단 자동 메타데이터에서 대조한다.

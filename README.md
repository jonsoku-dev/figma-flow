# Figma Flow

[제품 헌법](CONSTITUTION.md) · [Design 전용 설계서](specs/design-specialization/spec.md)

Figma에는 **Figma Flow 하나**를 등록합니다. 사용자가 대상 Design 파일(여러 탭 동시 실행 지원)에서 플러그인을 실행 세션마다 한 번 직접 열면, Codex가 localhost 명령으로 문맥을 읽고 작업을 준비·실행·검증합니다. 대화·승인·프로필 선언·결과 해석은 Codex에서 합니다. Figma 패널은 현재 파일·페이지·선택과 연결·실행 상태·원인별 진단(`플러그인 ID·포트·세대`)을 보여 주는 수동 뷰어입니다. 공식 Figma MCP는 필요하지 않습니다. [1회 설정·세션 사용·멀티탭 요약](docs/guide.md#quickstart-lifecycle)

“이 페이지를 지켜보고 내가 Figma에서 고치면 이 대화로 알려 줘”라고 요청할 수 있습니다. Codex는 변경된 노드의 현재 값을 다시 읽고, 연결된 그래프의 반영 후보와 충돌을 구분합니다. [실시간 역방향 동기화](docs/guide.md#live-change-sync)

메이저 버전은 배포할 Git 트리에서 기능 그래프, 정책·화면 파생본과 영역별 하드코딩 검토 근거가 모두 확인된 경우에만 패키징합니다. [메이저 통과 조건](CONTRIBUTING.md#major-ssot)

**[통합 사용 가이드](docs/guide.md)** · [English](docs/guide.md#english) · [日本語](docs/guide.md#japanese)

설치·폰트·시안 검토·본제작·그래프 왕복·업데이트·복구·회사 배포는 통합 가이드 한 곳에서 확인합니다.

```text
Figma Flow의 현재 검증된 릴리스 태그를 설치하고 실제 Figma 연결 테스트까지 진행해 줘.
https://github.com/jonsoku-dev/figma-flow.git의 docs/guide.md를 따라.
기존 작업과 작업공간 ID를 보존해. Figma Flow 최초 등록과 세션별 실행은 내가 할게.
그 뒤 localhost 제어와 실제 JSON으로 검증해. 구체적인 요청은 한 안으로 진행하고, 비교를 요청하면 내 선택을 기다려.
```

| 필요한 작업 | 가이드 위치 |
|---|---|
| API별 실행 경로·지원 근거·확인된 미구현 항목 | [공개 Plugin API 1,382개 멤버 대조](library/figma-api/audit/report.md) |
| Figma 기능 찾기·로컬 예제 실행 | [기능별 경로](docs/guide.md#local-figma-features) · [`design-grid` 준비·실행](docs/figma-recipes.md#run-design-grid-through-figma-flow) |
| 처음 설치·고정 manifest 등록·첫 예제 | [설치부터 검토까지](docs/guide.md#2-클론하고-codex에-설치) |
| 한 번 실행한 뒤 Codex에서 관리 | [로컬 제어](docs/guide.md#기본-흐름-한-번-실행하고-codex에-맡기기) · [문맥·프로필·승인·결과](docs/guide.md#11-codex에서-대화-프로필-승인-결과-관리) |
| 선택한 원화·배치를 유지한 0.25.0 본제작 | [입력 핀과 verify-production](docs/guide.md#selected-rich-production) |
| 실제 Figma 값을 준비된 JSON으로 편집 | [native-edit 범위](docs/guide.md#prepared-native-edit) |
| 이미지·그라디언트 위 글자 대비 | [전체 배경 픽셀의 최소값과 판정 불가](docs/guide.md#contrast-evidence) |
| Figma·그래프·웹 왕복 | [동기화와 실제 증거](docs/guide.md#10-그래프와-figma-컴포넌트-동기화) · [G1 소스 재생성(0.35.0)](docs/guide.md#g1-source-regeneration) |
| 웹 캐러셀·탭·FAQ 프로토타입 | [캐러셀](docs/guide.md#web-carousel-quickstart) · [탭](docs/guide.md#web-tabs-quickstart) · [SaaS FAQ 아코디언(0.35.0)](docs/guide.md#web-disclosure-quickstart) |
| 시작 시 두 플러그인 최신화 | [자동 확인과 업데이트](docs/guide.md#automatic-startup) |
| graph 기반 사람용 스펙 설명 | [설명 보드와 기술 정보 분리](docs/guide.md#readable-specifications) |
| 새 릴리스·서비스 교체·복구 | [업데이트](docs/guide.md#updates) |
| 회사 Node/npm·private 배포 | [환경](docs/guide.md#environment) · [배포](docs/guide.md#private-distribution) |

`figma_control.py context`와 `profile get`으로 실제 세션 문맥과 사용자 선언을 확인합니다. 요청·승인·작업·읽기·검증 결과는 Codex에서 관리합니다. 실제 Figma 관찰·읽기·검증과 사용자 선택은 각각 별도 근거이며, 과거 화면이나 오프라인 테스트는 현재 실행 성공을 증명하지 않습니다.

개발·계약·전문 예제는 각각의 목적에 맞게 유지합니다.

- [개발 및 검사](CONTRIBUTING.md)와 [패널 개발](panel-ui/README.md).
- [디자인 실행 스킬](skills/figma-flow/SKILL.md), [연결 스킬](skills/figma-plugin-setup/SKILL.md), [그래프 계약](skills/figma-flow/references/graph-contract.md).
- [Graph SSOT 명령·지원 속성](examples/graph-ssot/README.md)과 [기록된 디자인 시스템 실험](docs/design-system-trials.md).
- [기능 스펙·요구사항·인수 조건](specs/README.md).
- [변경 기록](CHANGELOG.md)과 [동봉 외부 스킬 계약](skills/figma-flow/references/skill-dependencies.md).

## 라이선스와 참고

프로젝트 코드는 [MIT](LICENSE)입니다. 디자인 비평에는 Damir Sokolovsky([@heydamir](https://github.com/heydamir))의 [unslop](https://github.com/heydamir/unslop)을 각색해 사용합니다. 동봉 원문과 각색 문서는 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)이며 [출처](vendor/skills/unslop/CITATION.cff)·[라이선스](vendor/skills/unslop/LICENSE)·[변경 설명](skills/figma-flow/references/unslop.md)을 유지합니다. 제품의 작업·검증 계약에 맞게 적용했으며 원저자의 제품 보증을 뜻하지 않습니다.

UI 동작의 기준 자료는 [Figma 플러그인 실행 모델](https://developers.figma.com/docs/plugins/how-plugins-run/), [Figma 테마 변수](https://developers.figma.com/docs/plugins/css-variables/), [WAI-ARIA 탭 패턴](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)입니다.

## 개발을 이어가기

[과거 0.27 구현 계획 RD-01~09](docs/development-roadmap/README.md)와 [해당 인수 행렬](docs/development-roadmap/FINAL_ACCEPTANCE.md)은 당시 구현과 검증 범위를 보존합니다. **Historical 0.36.0 verification snapshot:** recorded P0 reference separation, P1 Design-only expansion (NF-01/NF-03), and the P2 first fresh-read baseline; mobile FAQ keyboard support, complex-render fidelity, and incremental native reads remained proposed. The `0.35.0` FAQ and P0 prototype/presentation observations remain historical evidence. The snapshot did not extend P2 playback claims; cloud sync and physical-device coverage remained out of scope. Current work is defined by the [next feature and improvement backlog](docs/next-roadmap/README.md), not by this past snapshot.

[작은손 커피공방](apps/little-hands/README.md)은 Django·PostgreSQL 기반의 독립 운영 앱입니다. 실제 인증·예약 트랜잭션·운영 화면과 Docker 패키지를 다루며 Figma Flow 자체의 런타임 의존성은 아닙니다. 22개 상태의 desktop/mobile 원본 캡처와 Figma의 전체 제작·편집·getter 인수는 구분합니다. 설치·공개 배포·실서비스 인수 상태는 해당 실행 근거를 확인합니다.

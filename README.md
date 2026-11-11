# Figma Flow

Figma에는 **Figma Flow 하나**를 등록합니다. 사용자가 대상 Design 파일에서 플러그인을 실행 세션마다 한 번 직접 열면, Codex가 이 플러그인의 localhost 명령으로 준비된 작업을 실행하고 실제 JSON을 검증합니다. 기본 소비자 경로에는 Computer Use나 공식 Figma MCP가 필요하지 않습니다.

**[통합 사용 가이드](docs/guide.md)** · [English](docs/guide.md#english) · [日本語](docs/guide.md#japanese)

설치·폰트·시안 검토·본제작·그래프 왕복·업데이트·복구·회사 배포는 통합 가이드 한 곳에서 확인합니다.

```text
Figma Flow v0.25.0을 설치하고 실제 Figma 연결 테스트까지 진행해 줘.
https://github.com/jonsoku-dev/figma-flow.git의 docs/guide.md를 따라.
기존 작업과 작업공간 ID를 보존해. Figma Flow 최초 등록과 세션별 실행은 내가 할게.
그 뒤 localhost 제어와 실제 JSON으로 검증해. 구체적인 요청은 한 안으로 진행하고, 비교를 요청하면 내 선택을 기다려.
```

| 필요한 작업 | 가이드 위치 |
|---|---|
| 처음 설치·고정 manifest 등록·첫 예제 | [설치부터 검토까지](docs/guide.md#2-클론하고-codex에-설치) |
| 한 번 실행한 뒤 Codex에 맡기기 | [로컬 제어](docs/guide.md#기본-흐름-한-번-실행하고-codex에-맡기기) |
| 선택한 원화·배치를 유지한 0.25.0 본제작 | [입력 핀과 verify-production](docs/guide.md#selected-rich-production) |
| 실제 Figma 값을 준비된 JSON으로 편집 | [native-edit 범위](docs/guide.md#prepared-native-edit) |
| 이미지·그라디언트 위 글자 대비 | [전체 배경 픽셀의 최소값과 판정 불가](docs/guide.md#contrast-evidence) |
| Figma·그래프·웹 왕복 | [동기화와 실제 증거](docs/guide.md#10-그래프와-figma-컴포넌트-동기화) |
| 시작 시 두 플러그인 최신화 | [자동 확인과 업데이트](docs/guide.md#automatic-startup) |
| graph 기반 사람용 스펙 설명 | [설명 보드와 기술 정보 분리](docs/guide.md#readable-specifications) |
| 새 릴리스·서비스 교체·복구 | [업데이트](docs/guide.md#updates) |
| 회사 Node/npm·private 배포 | [환경](docs/guide.md#environment) · [배포](docs/guide.md#private-distribution) |

홈의 **다음 작업**, **이력**, **한국어 / English / 日本語**로 상태와 언어를 확인합니다. 제어 연결을 사용할 수 없으면 패널 실행과 JSON 저장을 사용합니다. 실제 관찰·읽기·검증과 사용자 선택은 각각 별도 근거이며, 과거 화면이나 오프라인 테스트가 현재 Figma 실행 성공을 보증하지 않습니다.

개발·계약·전문 예제는 각각의 목적에 맞게 유지합니다.

- [개발 및 검사](CONTRIBUTING.md)와 [패널 개발](panel-ui/README.md).
- [디자인 실행 스킬](skills/figma-flow/SKILL.md), [연결 스킬](skills/figma-plugin-setup/SKILL.md), [그래프 계약](skills/figma-flow/references/graph-contract.md).
- [Graph SSOT 명령·지원 속성](examples/graph-ssot/README.md)과 [기록된 디자인 시스템 실험](docs/design-system-trials.md).
- [기능 스펙·요구사항·인수 조건](specs/README.md).
- [변경 기록](CHANGELOG.md)과 [동봉 외부 스킬 계약](skills/figma-flow/references/skill-dependencies.md).

## 라이선스와 참고

프로젝트 코드는 [MIT](LICENSE)입니다. 디자인 비평에는 Damir Sokolovsky([@heydamir](https://github.com/heydamir))의 [unslop](https://github.com/heydamir/unslop)을 각색해 사용합니다. 동봉 원문과 각색 문서는 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)이며 [출처](vendor/skills/unslop/CITATION.cff)·[라이선스](vendor/skills/unslop/LICENSE)·[변경 설명](skills/figma-flow/references/unslop.md)을 유지합니다. 제품의 작업·검증 계약에 맞게 적용했으며 원저자의 제품 보증을 뜻하지 않습니다.

UI 동작의 기준 자료는 [Figma 플러그인 실행 모델](https://developers.figma.com/docs/plugins/how-plugins-run/), [Figma 테마 변수](https://developers.figma.com/docs/plugins/css-variables/), [WAI-ARIA 탭 패턴](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)입니다.

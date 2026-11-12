<!-- patch-knowledge
{"commit":"1c3acdffcaccb373eed12559d5caa83b3f4fc83f","diff_sha256":"f6675cc81decbdcc29be15b9ba47650a47f75e39e059a006be63e4267599e7ba","files":[".codex-plugin/plugin.json","README.md","plugin.json","skills/figma-flow/SKILL.md","tests/test_check_project.py","tests/test_design_bundle.py","tests/test_figma_draft.py","tests/test_regressions_0180.py","tools/check_project.py","tools/design_actions.py","tools/design_bundle.py","tools/embedded_assets.py","tools/figma_bridge.py","tools/figma_draft.py"],"parents":["b81736ee077734337d39c2b065ad935e698ea046","f33249fa960d8666dfda75be5b493de4846bb6a4"],"subject":"Merge release/0.18.0","tree":"1be6d923d85daa64295e65e4ad16b66a97207d66","versions":[{"path":"plugin.json","version":"0.18.0"},{"path":".codex-plugin/plugin.json","version":"0.18.0"}]}
-->
# 1c3acdf · 0.18.0 릴리스 병합

- 커밋: `1c3acdffcaccb373eed12559d5caa83b3f4fc83f`
- 원문 제목: Merge release/0.18.0
- 계보 유형: 병합 커밋; 이 문서는 역사적 계보 기록이며 현행 릴리스 선언이 아니다.

## 문제와 계기

이 커밋은 0.18.0 릴리스 통합 계보를 보존한다. 첫 부모 기준 차이는 아래에 열거하며 이 merge만으로 별도 런타임 실행을 주장하지 않는다.

## 결과 동작

첫 부모 기준 14경로가 달라진다. check_project의 selected Figma readback/evidence freshness 보고, embedded image 크기 검사와 bridge/draft/bundle 연결 변경이 있고 README/manifest는 0.18.0으로 갱신된다.

## 변경 파일과 인터페이스

`.codex-plugin/plugin.json`, `README.md`, `plugin.json`, `skills/figma-flow/SKILL.md`, `tests/test_check_project.py`, `tests/test_design_bundle.py`, `tests/test_figma_draft.py`, `tests/test_regressions_0180.py`, `tools/check_project.py`, `tools/design_actions.py`, `tools/design_bundle.py`, `tools/embedded_assets.py`, `tools/figma_bridge.py`, `tools/figma_draft.py`가 첫 부모 diff 경로다.

## 설계 이유와 출처

정확한 부모 순서: `b81736ee077734337d39c2b065ad935e698ea046` (첫 부모), `f33249fa960d8666dfda75be5b493de4846bb6a4` (둘째 부모). 첫 부모는 0.17.6 계열, 두 번째 부모는 0.18.0 기능 커밋이다. [기능 변경 기록](f33249fa960d8666dfda75be5b493de4846bb6a4.md)과 경로별 실제 변경을 구분한다.

## 호환성·이관·복구

체크/build가 evidence와 embedded image 상태에 따라 실패할 수 있다. 이 merge의 테스트 파일 변경은 존재하지만 실제 선택 Figma readback이나 사용자 프로젝트 검증을 입증하지 않는다.

## 검증과 미검증

첫 부모 diff 확인. 테스트 실행과 Figma readback 미검증.

## 한계와 후속 개선

이 기록은 릴리스 브랜치 통합을 보존한다. 실행/배포를 완료했다는 의미는 아니다.

## 관련 기록

원본 Git 커밋 `1c3acdffcaccb373eed12559d5caa83b3f4fc83f`의 첫 부모 diff 및 merge 부모를 확인했다. 원본 Git 커밋 `1c3acdffcaccb373eed12559d5caa83b3f4fc83f`; source bundle SHA-256 `69aac71126cd34c9a451e091e134aec80ca6a9d401485830567c2869e8017192`.
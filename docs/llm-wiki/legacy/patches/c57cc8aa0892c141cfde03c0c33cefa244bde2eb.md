<!-- patch-knowledge
{"commit":"c57cc8aa0892c141cfde03c0c33cefa244bde2eb","diff_sha256":"d7c91b9adf6f33c9ab9d0fe0e085e981c9bb6ef03a016fa6589f06b6611ac40f","files":[".codex-plugin/plugin.json","README.md","plugin.json","skills/figma-flow/references/visual-quality.md","tests/test_design_quality.py","tools/design_quality.py"],"parents":["a36559aa505bce009d8075ce40bf6822080bebdf","953bbd9999d0a01001c50916b074c28c836a1360"],"subject":"Merge release/0.17.1: Figma Flow 0.17.1","tree":"768432a02c1073c22f0e8a08a541511974340887","versions":[{"path":"plugin.json","version":"0.17.1"},{"path":".codex-plugin/plugin.json","version":"0.17.1"}]}
-->
# c57cc8a · 0.17.1 릴리스 병합

- 커밋: `c57cc8aa0892c141cfde03c0c33cefa244bde2eb`
- 원문 제목: Merge release/0.17.1: Figma Flow 0.17.1
- 계보 유형: 병합 커밋; 이 문서는 역사적 계보 기록이며 현행 릴리스 선언이 아니다.

## 문제와 계기

이 커밋은 0.17.1 품질 변경 통합 계보를 보존한다. 첫 부모 기준 차이는 아래에 열거하며 이 merge만으로 별도 런타임 실행을 주장하지 않는다.

## 결과 동작

첫 부모 기준 6경로를 반영했다. `design_quality.py`와 회귀 테스트가 품질 검사 동작을 확장하고, `visual-quality.md`가 이를 설명하며, README와 두 manifest가 0.17.1 버전을 표시한다. 릴리스 브랜치의 구체 기능 근거는 [0.17.1 품질 릴리스 기록](953bbd9999d0a01001c50916b074c28c836a1360.md)과 이 merge diff다.

## 변경 파일과 인터페이스

`plugin.json`, `.codex-plugin/plugin.json`, `README.md`, `skills/figma-flow/references/visual-quality.md`, `tests/test_design_quality.py`, `tools/design_quality.py`가 첫 부모 diff 경로다.

## 설계 이유와 출처

정확한 부모 순서: `a36559aa505bce009d8075ce40bf6822080bebdf` (첫 부모), `953bbd9999d0a01001c50916b074c28c836a1360` (둘째 부모). 첫 부모는 0.17.0 통합 트리이고 두 번째 부모는 0.17.1 릴리스 브랜치다. 병합 결과는 첫 부모 대비 위 여섯 경로를 변경하며, 두 manifest는 0.17.1로 바뀐다.

## 호환성·이관·복구

품질 검사 입력에 대한 검증 동작이 바뀔 수 있으므로 기존 authored layout이 새 검사에서 실패할 수 있다. 이 merge 자체에서 데이터 마이그레이션은 확인되지 않는다.

## 검증과 미검증

첫 부모 diff 확인. 테스트 실행과 시각 품질의 실제 결과는 미검증.

## 한계와 후속 개선

별도 merge 페이지는 릴리스 이력을 보존한다. 동작의 세부 설명은 해당 구현 변경 커밋 기록을 따른다.

## 관련 기록

원본 Git 커밋 `c57cc8aa0892c141cfde03c0c33cefa244bde2eb`의 첫 부모 diff 및 merge 부모를 확인했다. 원본 Git 커밋 `c57cc8aa0892c141cfde03c0c33cefa244bde2eb`; source bundle SHA-256 `69aac71126cd34c9a451e091e134aec80ca6a9d401485830567c2869e8017192`.
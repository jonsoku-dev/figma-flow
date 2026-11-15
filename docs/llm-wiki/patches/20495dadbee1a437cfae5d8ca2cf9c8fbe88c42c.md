<!-- patch-knowledge
{"commit":"20495dadbee1a437cfae5d8ca2cf9c8fbe88c42c","diff_sha256":"162e2ff92c184958454cbadc282ae3706c9c303fa64ce86f65c051f74897223d","files":["README.md","docs/development-roadmap/FINAL_ACCEPTANCE.md","docs/guide.md"],"parents":["310f6573b4c60a78a4da0099c0f91976430323da"],"subject":"docs(release): clarify Design presentation scope and P2 playback limits","tree":"54c39d6f3abaab8e9c0789fde831c1b04f3eb6ae","versions":[{"path":"plugin.json","version":"0.36.0"},{"path":".codex-plugin/plugin.json","version":"0.36.0"}]}
-->

# docs(release): clarify Design presentation scope and P2 playback limits

## 문제와 계기

`310f6573b4c60a78a4da0099c0f91976430323da`의 한계 요약이 프레젠테이션 재생 자체를 범위 외처럼 표기해 `CONSTITUTION.md`의 Design 프로토타입·프레젠테이션 범위 및 기존에 검증된 `0.35.0` FAQ·P0 프레젠테이션 증명과 충돌할 수 있었다.

## 결과 동작

커밋 `20495dadbee1a437cfae5d8ca2cf9c8fbe88c42c`는 `README.md`, `docs/guide.md`(KR/EN/JA), `docs/development-roadmap/FINAL_ACCEPTANCE.md`에서 프레젠테이션 일괄 제외 문구를 수정해, 기존 `0.35.0` FAQ·P0 프로토타입/프레젠테이션 검증 근거는 유지하고 **P2/`0.36.0`에서 새 재생 주장이나 확장 범위가 없음**을 명시했다.

## 변경 파일과 인터페이스

`README.md`, `docs/guide.md`, `docs/development-roadmap/FINAL_ACCEPTANCE.md`.

## 설계 이유와 출처

이력 보존 원칙(`no amend`)에 따라 `310f657`을 덮어쓰지 않고 별도 후속 커밋으로 사실관계를 교정했으며, Design Dev Mode 인계와 Design 파일 내 프로토타입 프레젠테이션을 일괄 제외하지 않는 제품 헌법과 정렬했다.

## 호환성·이관·복구

문서 문구 교정 전용이며 매니페스트(`0.36.0`), 코드, 백로그 상태를 바꾸지 않는다. `main`에 FF·push되어 `0.36.0` 통합 소스 기준 SHA가 됐다.

## 검증과 미검증

`20495da` 위에서 대상 Python 136건(`tests.test_design_specialization`, `tests.test_plugin_startup`, `tests.test_next_roadmap_backlog`, `tests.test_reference_distribution_guard`, `tests.test_patch_knowledge`, `tests.test_patch_knowledge_legacy`, `tests.test_skill_dependencies`, `tests.test_audit_dependencies`, `tests.test_check_project`, `tests.test_api_priority`, `tests.test_patch_knowledge_check`), Node 16건, `skill_dependencies.py --check`, `reference_distribution_guard.py --ref HEAD` 및 `git archive` ZIP dry-run이 통과했다. root의 단계별 native·패키지·최종 CI·태그 배포(`v0.36.0`) 검증은 별도 진행·대기 상태다.

## 한계와 후속 개선

`p2-faq-mobile-keyboard`, `p2-complex-render-fidelity`, `p2-incremental-native-read`는 `proposed`로 남으며 원격 클라우드 자동 동기화·실물 물리 기기·공개 DNS/TLS·사람의 창작 품질/production admission은 계속 범위 밖이다.

## 관련 기록

[0.36.0 릴리스 기록](../releases.md#v0.36.0) · [310f657](310f6573b4c60a78a4da0099c0f91976430323da.md) · [제품 헌법](../../../CONSTITUTION.md)

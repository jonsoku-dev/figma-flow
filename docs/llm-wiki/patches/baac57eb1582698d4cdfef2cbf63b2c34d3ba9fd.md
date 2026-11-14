<!-- patch-knowledge
{"commit":"baac57eb1582698d4cdfef2cbf63b2c34d3ba9fd","diff_sha256":"73637018b7ee978d2c8197c446ce42bee620002c0e6a3a1f991c63fdf43e8aa0","files":["apps/little-hands/design/source.py","examples/owned-component-families/README.md","examples/owned-component-families/design.json","examples/owned-component-families/graph.json","examples/owned-component-families/index.html","examples/owned-component-families/manifest.json","examples/owned-component-families/prepare.py","examples/owned-component-families/renderer.js","examples/owned-component-families/styles.css","tests/test_nf01_app_mapping.py"],"parents":["b40278221d8c023249462cd628edbdc51c0b041f"],"subject":"Add graph-owned six-family handoff example and accessible form/table browser checks","tree":"fd427a4676cffc8b5c28530a7c3ce975a5df46dc","versions":[{"path":"plugin.json","version":"0.35.0"},{"path":".codex-plugin/plugin.json","version":"0.35.0"}]}
-->

# Add graph-owned six-family handoff example and accessible form/table browser checks

## 문제와 계기

외부 비공개 레퍼런스나 앱 사본을 오염시키지 않고 6개 시맨틱 패밀리 핸드오프와 폼·테이블 접근성(`label` 포커스, `checkbox`, `radio` 형제 상태, `table` `caption`/`th`, 비활성 필드, 미선언 상태)을 end-to-end로 증명할 자체 공개 예제가 필요했다.

## 결과 동작

커밋 `baac57eb1582698d4cdfef2cbf63b2c34d3ba9fd`는 `examples/owned-component-families/`에 그래프 소유 6패밀리 웹·디자인 입력과 `prepare.py`를 신설하고, `apps/little-hands/design/source.py`·`tests/test_nf01_app_mapping.py`로 앱 매핑과 접근성 계약 검사를 연결했다.

## 변경 파일과 인터페이스

`examples/owned-component-families/{README.md,design.json,graph.json,index.html,manifest.json,prepare.py,renderer.js,styles.css}`, `apps/little-hands/design/source.py`, `tests/test_nf01_app_mapping.py`를 추가·수정했다.

## 설계 이유와 출처

P0 자체 공개 기준 입력(`examples/owned-design-baseline/`)과 동일한 원칙으로 비공개 샘플명·개인 경로 없이 재현 가능한 핸드오프 기준 예제를 구성했다.

## 호환성·이관·복구

기존 `examples/owned-design-baseline/`과 독립적으로 동작한다. 생성 산출물은 `prepare.py`로 재생성할 수 있다.

## 검증과 미검증

`tests/test_nf01_app_mapping.py` 및 P1 전체 Python 테스트가 `e6f4fd8`까지 통과했으며, 최종 인수 시 로컬 loopback `examples/owned-component-families/` 실시간 브라우저 화면에서 label-focus, checkbox, radio sibling+`ArrowUp`, table `Enter`·`caption`·`th`, disabled field, undeclared action 보존(`external_requests=[]`, `console_or_page_errors=[]`)을 직접 확인했다. 외부 도메인 브라우저 범용 호환성은 주장 범위 밖이다.

## 한계와 후속 개선

Figma Desktop 내 실제 `COMPONENT_SET`·인스턴스 생성과 readback 보장은 후속 `cfc7fbd1`·`709f1104`·`974b5de7`·`e6f4fd8` 커밋에서 구현됐다.

## 관련 기록

[미배포 P1 기록](../releases.md#p1-design-acceptance) · [자체 예제 안내](../../../examples/owned-component-families/README.md) · [최종 브라우저 인수 452acf1](452acf1302bdc37269a31977773a7f277e45d212.md)

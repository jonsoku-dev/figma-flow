<!-- patch-knowledge
{"commit":"bacb81cbe48f1afdad79bcc135778af4ffe1c2b4","diff_sha256":"6568826d193357e1a4675edaf32b166aec950bbacf4710734ec32dc8f09bbdc4","files":["tests/test_responsive_web_graph.py"],"parents":["3491b7d3d2971826f3f4cba89067cceffb91940d"],"subject":"test: verify viewport identity and bounded selection from larger graphs","tree":"b85827560e9396f130e075bb1d28ecfaa1f519fc","versions":[{"path":"plugin.json","version":"0.30.0"},{"path":".codex-plugin/plugin.json","version":"0.30.0"}]}
-->

# test: verify viewport identity and bounded selection from larger graphs

## 문제와 계기

큰 반응형 graph에서 route·viewport 관계가 올바르게 묶이고, 한 네이티브 계획이 지원 한도보다 많은 화면을 선택하지 않는지 고정 회귀 기준이 없었다.

## 결과 동작

새 테스트는 18개 화면을 9개 route와 두 viewport에 묶고, 같은 route·viewport 중복을 거부하며, 16개 초과 선택을 거절하는 한편 명시한 두 화면 계획은 screen scope로 허용되는지 확인한다.

## 변경 파일과 인터페이스

`tests/test_responsive_web_graph.py`는 `web_route_graph.link_viewports`, `web_design.build_plan`, `native_edit.validate_plan`을 작은 fixture graph에서 연결 검증한다. 제품 코드는 변경하지 않는다.

## 설계 이유와 출처

원본 graph에는 최대 256개 측정 화면을 허용하되 한 native edit에서는 최대 16개까지만 계획한다. 테스트는 이 두 수를 구분하고 route별 viewport identity가 유지되는지 확인한다.

## 호환성·이관·복구

회귀 기준 추가만 포함하며 저장된 user graph, Figma 문서, 플러그인 버전에는 변경이 없다.

## 검증과 미검증

이 커밋의 clean checkout에서 `python3 -B -m unittest tests.test_responsive_web_graph` 2개가 통과했다. 실제 Figma 화면을 수정하거나 읽지는 않는다.

## 한계와 후속 개선

이 fixture는 route grouping과 selection bound를 확인한다. 실제 페이지의 모든 route, CSS 대응 또는 실제 native readback 품질을 증명하지 않는다.

## 관련 기록

[route·viewport 구현](5f1842e2a904583813db63dc3adc402a5cb31318.md) · [screen readback contract](2a5bec07b6b887e4ef8ee40582484ae2a3d0b0cc.md).

원문 대조는 `git show bacb81cbe48f1afdad79bcc135778af4ffe1c2b4`로 한다.

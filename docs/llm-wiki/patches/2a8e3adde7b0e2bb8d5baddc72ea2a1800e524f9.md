<!-- patch-knowledge
{"commit":"2a8e3adde7b0e2bb8d5baddc72ea2a1800e524f9","diff_sha256":"5401e5e4ad539ed474e1f24a920e63a4fd90a16e4f69394e4a545d7f345025b4","files":["apps/little-hands/design/README.md","apps/little-hands/design/source-status.json","apps/little-hands/design/source.py","apps/little-hands/design/test_regeneration.py"],"parents":["c89403fd4dd5923eb633ff079bf62db4f22861f1"],"subject":"fix: complete G1 token ownership, state insertion, and orphan candidate reporting","tree":"06a0fb1c4ff02c7d791ada2f7c346ce2116911f1","versions":[{"path":"plugin.json","version":"0.34.0"},{"path":".codex-plugin/plugin.json","version":"0.34.0"}]}
-->

# fix: complete G1 token ownership, state insertion, and orphan candidate reporting

## 문제와 계기

요구사항 목록이 바뀌거나 채택한 디자인 토큰이 있는 그래프를 재생성할 때 생성기와 작성자가 소유한 값을 구분해야 했다.

## 결과 동작

중첩 역할과 프로토타입 상태·바인딩을 식별자로 맞추고, 소스에서 빠진 노드와 관계를 기존 검토 근거와 함께 삭제 후보로 보고한다.

## 변경 파일과 인터페이스

apps/little-hands/design/source.py의 reconcile과 build, source-status.json의 orphan_candidates, 같은 폴더의 README 및 test_regeneration.py가 변경됐다.

## 설계 이유와 출처

목록의 위치는 항목 삽입으로 바뀌므로 식별자·이전 생성 후보·현재 정본을 사용해 변경을 비교한다.

## 호환성·이관·복구

기존 그래프의 노드와 관계는 유지한다. 생성 원본이 없는 항목 중 기존 후보와 사람이 추가한 항목을 구분한다.

## 검증과 미검증

디자인 테스트 23개가 통과했다. 독립 검사에서는 REQ-006을 제외한 첫 성공에 후보 13개가 생겼지만 CSS epoch 오류 뒤 정상 재시도 시 0개가 됐다.

## 한계와 후속 개선

재시도 분류 결함은 이 커밋에 남았다. bfb5e8f가 차단 상태 기록을 수정했다.

## 관련 기록

[G1 재생성 계약](../../STARTER_ROLE_FEATURE_SPEC.md) · [미배포 변경](../releases.md#g1-source-regeneration).

원문 대조는 `git show 2a8e3adde7b0e2bb8d5baddc72ea2a1800e524f9`로 한다.

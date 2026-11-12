<!-- patch-knowledge
{"commit":"dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d","diff_sha256":"a6ae190d076875635465ff370617c326aaa1539497db521796a9c563533d41d0","files":["docs/llm-wiki/catalog.json","docs/llm-wiki/patches/0ce837ccf732354cf2a0f94cbb42042c9ca6fda2.md","docs/llm-wiki/patches/4ef1c8e5c6b038ea26f097d67a962daf4ae6f477.md","docs/llm-wiki/patches/cc53d88e91da49ac33c54c720b1be228b78c93bd.md"],"parents":["0ce837ccf732354cf2a0f94cbb42042c9ca6fda2"],"subject":"docs: record stable change identities apart from selection order","tree":"0ee6a2cf8a18c22f937eb87d8b76fa05d249710d","versions":[{"path":"plugin.json","version":"0.26.3"},{"path":".codex-plugin/plugin.json","version":"0.26.3"}]}
-->
# docs: record stable change identities apart from selection order

## 문제와 계기

선택 직렬화 구현 0ce837ccf732354cf2a0f94cbb42042c9ca6fda2 뒤에는 실패 기준 cc53d88e91da49ac33c54c720b1be228b78c93bd와 이전 발행 4ef1c8e5c6b038ea26f097d67a962daf4ae6f477의 상세 페이지가 커밋되지 않았다. 이 커밋 dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d는 그 기록을 카탈로그에 남긴다.

## 결과 동작

docs/llm-wiki/catalog.json이 stable change identity까지 맞춰진다. docs/llm-wiki/patches/4ef1c8e5c6b038ea26f097d67a962daf4ae6f477.md, docs/llm-wiki/patches/cc53d88e91da49ac33c54c720b1be228b78c93bd.md, docs/llm-wiki/patches/0ce837ccf732354cf2a0f94cbb42042c9ca6fda2.md가 추가된다. 값을 쓰지 않는 직렬화는 사용자 CHANGELOG 항목으로 적지 않았다.

## 변경 파일과 인터페이스

docs/llm-wiki/catalog.json과 위 세 페이지를 추가했다. 제품 코드와 검사는 포함하지 않는다.

## 설계 이유와 출처

패치 기록 계약은 구현과 문서 발행을 나눈다. 패널에 아직 보이지 않는 identity는 화면 변화로 적지 않는다.

## 호환성·이관·복구

기록 추가만 한다. 기존 전체 적용 경로와 플러그인 버전은 이 커밋이 바꾸지 않는다.

## 검증과 미검증

발행 직후 verify --ref HEAD는 커밋 119개와 문서 발행 1개를 통과했다. Figma 패널 선택은 관찰하지 않았다.

## 한계와 후속 개선

이 페이지는 이후 카탈로그가 dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d 자신을 포함할 때 비어 있던 항목을 채운다. 선택 수와 영향 target 행은 이 기록의 범위 밖이다.

## 관련 기록

[선택 직렬화](0ce837ccf732354cf2a0f94cbb42042c9ca6fda2.md), [실패 기준](cc53d88e91da49ac33c54c720b1be228b78c93bd.md). 원문은 git show dc1ce4ebd586c452f66c4526acfc4e0b2dbd6e3d로 대조한다.

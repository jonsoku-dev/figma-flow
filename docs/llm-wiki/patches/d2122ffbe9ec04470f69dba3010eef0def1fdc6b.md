<!-- patch-knowledge
{"commit":"d2122ffbe9ec04470f69dba3010eef0def1fdc6b","diff_sha256":"9170fb6a4dcf12dbef4d3807d48f794e96a09642c15f4ad83a2d90f97592bf66","files":["docs/llm-wiki/catalog.json","docs/llm-wiki/patches/4ebdb77a73746f95dc985507b2ba0d704975cf9c.md","docs/llm-wiki/patches/a0f790602dc1a2b6b6efaaf4623b14dc7461faa8.md","docs/llm-wiki/patches/c7a4dfffb39aaa26eca0f6571a3bf0af97762822.md"],"parents":["4ebdb77a73746f95dc985507b2ba0d704975cf9c"],"subject":"docs: record declared hug, fill, and fixed sizing refresh","tree":"e18f3f3348a864f63b7c1ae8c7f8c70313f2f62c","versions":[{"path":"plugin.json","version":"0.26.3"},{"path":".codex-plugin/plugin.json","version":"0.26.3"}]}
-->
# docs: record declared hug, fill, and fixed sizing refresh

## 문제와 계기

크기 갱신 구현 4ebdb77a73746f95dc985507b2ba0d704975cf9c 뒤에는 실패 기준 c7a4dfffb39aaa26eca0f6571a3bf0af97762822와 이전 발행 a0f790602dc1a2b6b6efaaf4623b14dc7461faa8의 상세 페이지가 커밋되지 않았다. 이 커밋 d2122ffbe9ec04470f69dba3010eef0def1fdc6b는 그 기록을 카탈로그에 남긴다.

## 결과 동작

docs/llm-wiki/catalog.json이 크기 갱신까지 맞춰진다. docs/llm-wiki/patches/4ebdb77a73746f95dc985507b2ba0d704975cf9c.md, docs/llm-wiki/patches/a0f790602dc1a2b6b6efaaf4623b14dc7461faa8.md, docs/llm-wiki/patches/c7a4dfffb39aaa26eca0f6571a3bf0af97762822.md가 추가된다. 실제 글꼴 측정은 관찰하지 않았다고 적는다.

## 변경 파일과 인터페이스

docs/llm-wiki/catalog.json과 위 세 페이지를 추가했다. 제품 코드와 검사는 포함하지 않는다.

## 설계 이유와 출처

패치 기록 계약은 구현과 문서 발행을 나눈다. mock 상자 갱신은 사용자 CHANGELOG 항목으로 적지 않았다.

## 호환성·이관·복구

기록 추가만 한다. 기존 방향 패킷, node ID, prototype target은 이 커밋이 바꾸지 않는다.

## 검증과 미검증

발행 직후 verify --ref HEAD는 커밋 80개와 문서 발행 1개를 통과했다. 실제 글꼴 측정과 Figma reflow는 관찰하지 않았다.

## 한계와 후속 개선

이 페이지는 이후 카탈로그가 d2122ffbe9ec04470f69dba3010eef0def1fdc6b 자신을 포함할 때 비어 있던 항목을 채운다. 제어 상태 전이 fixture는 이 기록의 범위 밖이다.

## 관련 기록

[크기 갱신](4ebdb77a73746f95dc985507b2ba0d704975cf9c.md), [실패 기준](c7a4dfffb39aaa26eca0f6571a3bf0af97762822.md). 원문은 git show d2122ffbe9ec04470f69dba3010eef0def1fdc6b로 대조한다.

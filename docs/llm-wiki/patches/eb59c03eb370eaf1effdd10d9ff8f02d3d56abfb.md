<!-- patch-knowledge
{"commit":"eb59c03eb370eaf1effdd10d9ff8f02d3d56abfb","diff_sha256":"8324c4268aa7756957549c7699566a75593071add9856c1d76ee4487d92f176e","files":["CHANGELOG.md","docs/llm-wiki/catalog.json","docs/llm-wiki/patches/0fc65bae7c72d818abfb8ec27d6cd309f67e43f2.md","docs/llm-wiki/patches/104652403ef26368729086588387e9fae7dfe4ac.md","docs/llm-wiki/patches/2078ea9a94edd1f1c652953f30819c4fae50d20d.md","docs/llm-wiki/patches/2f58c8c1722a67e15a08180dc97e424a6e2a91a4.md","docs/llm-wiki/patches/428a358688a50116956006b734b5ad850c88bbf6.md","docs/llm-wiki/patches/561d1c9f25516f4e6c44b6e75047e39a7e86afa3.md","docs/llm-wiki/patches/59dba566f4982923076ef0ed22cc0da5f60f42c5.md","docs/llm-wiki/patches/5e89c53918a01646bd693fcd96cef5502d0e8718.md","docs/llm-wiki/patches/61647d636f23142c76d453f24512566043c40517.md","docs/llm-wiki/patches/7aef05e416b625ccab46122d8d0720e45e9471a5.md","docs/llm-wiki/patches/91e394ca399a987bccff4e785e1c49964e153fdd.md","docs/llm-wiki/patches/a13e89c27c16108e4fb75a446154636124312c4d.md","docs/llm-wiki/patches/a46a608d94731afdf0af5f1214d6e7b00dd495af.md","docs/llm-wiki/patches/bcf2dd6434c0650b91f7e5d78e47b04ba6d0e1b3.md","docs/llm-wiki/releases.md"],"parents":["7aef05e416b625ccab46122d8d0720e45e9471a5"],"subject":"docs: publish 0.33.0 carousel release notes and fork evidence","tree":"b0449a3d5a822c915e8a56f2c47f98371e66d000","versions":[{"path":"plugin.json","version":"0.33.0"},{"path":".codex-plugin/plugin.json","version":"0.33.0"}]}
-->


# docs: publish 0.33.0 carousel release notes and fork evidence

## 문제와 계기

0.33.0 캐러셀 코드와 실제 인수가 끝난 뒤, 사용자용 변경 기록과 포크가 읽을 커밋별 근거가 비어 있었다.

## 결과 동작

`CHANGELOG.md`에 0.33.0 사용자 변화 네 줄을, `docs/llm-wiki/releases.md`에 v0.33.0 절을 추가했다. `docs/llm-wiki/catalog.json`과 0.33 구간 커밋별 패치 페이지 13개가 생성·작성됐다.

## 변경 파일과 인터페이스

변경 경로는 `CHANGELOG.md`, `docs/llm-wiki/catalog.json`, `docs/llm-wiki/releases.md`, `docs/llm-wiki/patches/` 아래 13개 페이지다. 제품 코드와 인터페이스 변화는 없다.

## 설계 이유와 출처

패치 기록 계약에 따라 짧은 사용자 변화와 상세 근거를 분리했다. 이 페이지는 0.34 세션에서 sync가 해당 커밋을 새로 포착해 작성했다. 당시 작성 세션의 추가 판단은 미상이다.

## 호환성·이관·복구

문서와 기록 파일만 바꿨다. 되돌려도 플러그인 동작은 바뀌지 않는다.

## 검증과 미검증

0.34 세션에서 `git show --stat`로 변경 경로를 대조했다. 당시 `patch_knowledge.py verify` 실행 결과는 이 세션에서 다시 확인하지 않았으므로 미검증으로 둔다.

## 한계와 후속 개선

자기 자신의 패치 페이지는 같은 커밋에 들어갈 수 없어 다음 발행에서 작성된다.

## 관련 기록

[버전 기록](../releases.md#v0.33.0).

원문 대조는 `git show eb59c03eb370eaf1effdd10d9ff8f02d3d56abfb`로 한다.

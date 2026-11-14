<!-- patch-knowledge
{"commit":"dc05491e35c3fb0aeacd2b0dcded57c0f45c07a4","diff_sha256":"4b6810600ba40e56b238e538a0b53ac79cc87218229ba88ce23e10161cb4662e","files":["docs/llm-wiki/catalog.json","docs/llm-wiki/patches/3c99d8ae62d6943ac5fc266e16e72c5f037ff4a6.md","docs/llm-wiki/patches/42264f1a145b85b3da13c146cf14a79c83f546f2.md","docs/llm-wiki/patches/61937dc11c4540bc3c5e88412f449389470647d8.md","docs/llm-wiki/patches/b08a778410917942eae007572834688bfd60d1cc.md","docs/llm-wiki/patches/e1e228cc1139f48120d32f04dc01362a98e15854.md","docs/llm-wiki/patches/e218e68b9870dde760cb2d5ae27e05b817ee58d9.md","docs/llm-wiki/patches/ea1b24831175c123553276a804101e824a3267b0.md","docs/llm-wiki/patches/eb59c03eb370eaf1effdd10d9ff8f02d3d56abfb.md","docs/llm-wiki/patches/f27863defeab1367eb4e74a9ecf5c2fa553e5b1a.md"],"parents":["b08a778410917942eae007572834688bfd60d1cc"],"subject":"docs: record the 0.34.0 tab patches in the embedded wiki","tree":"d656e3dde6be7952b6025eea04ce9670fb318f3d","versions":[{"path":"plugin.json","version":"0.34.0"},{"path":".codex-plugin/plugin.json","version":"0.34.0"}]}
-->


# docs: record the 0.34.0 tab patches in the embedded wiki

## 문제와 계기

0.34.0 구간의 아홉 커밋에 포크가 읽을 근거 페이지가 없어 기록 검사가 실패했다.

## 결과 동작

`docs/llm-wiki/patches/` 아래 아홉 페이지와 `docs/llm-wiki/catalog.json`을 작성했다. 각 페이지는 실제 diff·실행 결과·미검증 범위를 나눠 적는다.

## 변경 파일과 인터페이스

변경 경로는 `docs/llm-wiki/catalog.json`과 `docs/llm-wiki/patches/` 아래 아홉 페이지다. 제품 코드와 인터페이스 변화는 없다.

## 설계 이유와 출처

패치 기록 계약의 여덟 항목을 같은 세션의 실행 기록으로 채웠다. 0.33 발행 커밋 페이지는 당시 판단을 미상으로 남겼다.

## 호환성·이관·복구

문서와 카탈로그만 바꿨다. 되돌리면 기록 검사가 다시 실패하지만 플러그인 동작은 같다.

## 검증과 미검증

`patch_knowledge.py verify --ref HEAD`가 333개 커밋을 확인했고 `test_patch_knowledge*.py`가 통과했다.

## 한계와 후속 개선

이 커밋 자신의 페이지는 같은 커밋에 넣을 수 없어 다음 기록 커밋에서 작성한다.

## 관련 기록

[탭 인수 기록](../../../specs/interactive-web/tabs.md) · [버전 기록](../releases.md#v0.34.0).

원문 대조는 `git show dc05491e35c3fb0aeacd2b0dcded57c0f45c07a4`로 한다.

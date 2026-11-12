<!-- patch-knowledge
{"commit":"dacfdc577faed0cb155e1b30620cc9265ba4d1bb","diff_sha256":"877ad80b575fa1243eb73d6448b085d18e1bfbfae8a00088d23d4f4abade9b21","files":["CHANGELOG.md","docs/llm-wiki/catalog.json","docs/llm-wiki/patches/015f440ee635d817f033dddabb504acaea69895f.md","docs/llm-wiki/patches/73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2.md","docs/llm-wiki/patches/ab8b1fe594b960fb2b22936dff34e3b7e711ff21.md","docs/llm-wiki/patches/af2a027d7bebe176de697878f3b36d191ef35fe9.md","docs/llm-wiki/patches/b275a28ad9b31347b7663485aabc93b19fb00f7b.md","docs/llm-wiki/releases.md"],"parents":["73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2"],"subject":"docs: record the partial read rejection and diagnostic export","tree":"2a18b02b0d2d8a878d75530cb7ea4793e344b61e","versions":[{"path":"plugin.json","version":"0.26.3"},{"path":".codex-plugin/plugin.json","version":"0.26.3"}]}
-->
# docs: record the partial read rejection and diagnostic export

## 문제와 계기

부분 읽기 거절 af2a027d7bebe176de697878f3b36d191ef35fe9와 진단 기록 73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2 뒤에는 각각의 실패 기준과 이전 발행 b275a28ad9b31347b7663485aabc93b19fb00f7b의 상세 페이지가 커밋되지 않았다. 이 커밋 dacfdc577faed0cb155e1b30620cc9265ba4d1bb는 그 기록과 사용자 CHANGELOG를 남긴다.

## 결과 동작

docs/llm-wiki/catalog.json이 부분 읽기 거절과 그래프 패널 진단 내보내기까지 맞춰진다. docs/llm-wiki/patches/af2a027d7bebe176de697878f3b36d191ef35fe9.md, docs/llm-wiki/patches/ab8b1fe594b960fb2b22936dff34e3b7e711ff21.md, docs/llm-wiki/patches/73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2.md, docs/llm-wiki/patches/015f440ee635d817f033dddabb504acaea69895f.md, docs/llm-wiki/patches/b275a28ad9b31347b7663485aabc93b19fb00f7b.md가 추가된다. CHANGELOG.md 0.26.3에 진단 기록과 부분 읽기 거절을 적고 실제 Figma 화면은 확인하지 않았다고 남긴다.

## 변경 파일과 인터페이스

CHANGELOG.md, docs/llm-wiki/catalog.json, docs/llm-wiki/releases.md와 위 다섯 페이지를 추가했다. 제품 코드와 검사는 포함하지 않는다.

## 설계 이유와 출처

패치 기록 계약은 짧은 사용자 변화와 상세 Wiki를 함께 남긴다. 실행한 게이트와 실제 Figma 패널 관찰을 같은 근거로 적지 않는다.

## 호환성·이관·복구

기록 추가만 한다. 플러그인 버전은 0.26.3으로 유지한다.

## 검증과 미검증

발행 직후 verify --ref HEAD는 커밋 154개와 문서 발행 1개를 통과했다. 실제 Figma 패널은 보지 않았다.

## 한계와 후속 개선

이 페이지는 기록 발행이다. session cache는 문서 변경 coverage를 확인하기 전에는 넣지 않는다.

## 관련 기록

[부분 읽기 거절](af2a027d7bebe176de697878f3b36d191ef35fe9.md), [진단 기록](73622ea4bd2f2b4392bcb6c75b6a7f7817c97ac2.md). 원문은 git show dacfdc577faed0cb155e1b30620cc9265ba4d1bb로 대조한다.

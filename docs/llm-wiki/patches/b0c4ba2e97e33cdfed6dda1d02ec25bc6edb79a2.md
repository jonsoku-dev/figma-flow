<!-- patch-knowledge
{"commit":"b0c4ba2e97e33cdfed6dda1d02ec25bc6edb79a2","diff_sha256":"bb59bbb2180e8347d8fb9feda2fbe2322da3b1ae12b9ce9153786be34b56c05e","files":["tests/helpers/relay_palette.mjs","tools/chromium_pipe.mjs"],"parents":["79ba8f68c9d95d035b28e4fe78fa68a9a8a73207"],"subject":"fix: verify relay themes in separate Chromium sessions","tree":"c353401a55557387efd54f0ae371bef1938f8b85","versions":[{"path":"plugin.json","version":"1.0.0"},{"path":".codex-plugin/plugin.json","version":"1.0.0"}]}
-->

# 실제 브라우저 프로필별 테마 검증

소스 커밋 `b0c4ba2e97e33cdfed6dda1d02ec25bc6edb79a2`

## 문제와 계기

호스팅된 Chromium은 이미 열린 페이지에서 미디어 모드를 바꿔도 밝은 스타일을 반환했다.

## 결과 동작

밝은 테마와 어두운 테마를 서로 독립적인 새 브라우저 세션에서 실행한다.

## 변경 파일과 인터페이스

`tests/helpers/relay_palette.mjs`와 `tools/chromium_pipe.mjs`를 갱신했다.

## 설계 이유와 출처

어두운 테마는 탐색 전 브라우저가 시작할 때 켜고 CSS의 실제 미디어 상태를 확인한다.

## 호환성·이관·복구

기존 브라우저 호출의 기본 옵션, 제품 CSS 색상과 치수의 기대값을 유지한다.

## 검증과 미검증

두 실제 Chromium 세션을 사용하는 같은 테스트를 네 번 실행해 모든 색과 치수를 확인했다.

## 한계와 후속 개선

최종 원격 후보에 대해서도 전체 테스트와 아카이브 검증을 다시 실행한다.

## 관련 기록

[실행 기록](../verification.md)

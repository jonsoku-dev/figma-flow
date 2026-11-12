<!-- patch-knowledge
{"commit":"c7a3cdef85ad0fdb7bade6a3fe5fa1e896864dd2","diff_sha256":"fec9ceb10cbf77295deb6e40e46a7c773c2d6e88b8ff6696030d9973cb643a13","files":["tests/finalize_scroll_clip.cjs","tests/finalize_scroll_clip.py"],"parents":["bbe11d2a80604207b8efaba5c521834acad779b3"],"subject":"test: pin native scroll clipping and readback contract","tree":"5d4051d972741491206976d4766349403516d56c","versions":[{"path":"plugin.json","version":"0.26.3"},{"path":".codex-plugin/plugin.json","version":"0.26.3"}]}
-->

# test: pin native scroll clipping and readback contract

## 문제와 계기

대형 표 등 명시적 스크롤 자식은 화면 밖 좌표가 정상일 수 있지만, 일반 clipping을 스크롤 허용으로 오인하면 우발적인 off-frame 결함까지 숨기게 된다.

## 결과 동작

Python/JS frozen oracle이 clipped Frame의 none/horizontal/vertical/both만 허용하고 실제 overflowDirection setter/getter 및 readback을 요구한다. 정상 축 overflow는 원시 좌표를 보존하며 geometry drift·잘못된 축·미선언 leaf는 계속 실패해야 한다.

## 변경 파일과 인터페이스

finalize_scroll_clip.py는 normalize_layer_containers/layout_errors/native_screen_findings를, CJS는 direction_review의 실제 preflight/placement/geometry/readDeclaredContainerLinks와 native_semantic_read를 호출한다. prototype getter fixture가 JSON 직렬화만으로는 얻지 못하는 API 속성 읽기를 검증한다.

변경 경로: [tests/finalize_scroll_clip.cjs](../../../tests/finalize_scroll_clip.cjs), [tests/finalize_scroll_clip.py](../../../tests/finalize_scroll_clip.py).

## 설계 이유와 출처

root clipping이나 조상 축의 단순 합집합은 중간 clip의 제한을 무시한다. nested horizontal-inner/vertical-outer 순서는 허용하되 반대 순서·ordinary inner는 거절해야 한다. native getter 부재·clip/overflow/type drift도 fail closed로 검사한다.

## 호환성·이관·복구

제품 구현이나 데이터를 바꾸지 않는 독립 기준 추가다. scroll 미선언 ordinary Frame의 기존 off-frame 차단을 유지하고 좌표 clamp로 실패를 숨기지 못하게 한다. API fixture가 실제 기기 관찰로 승격되지는 않는다.

## 검증과 미검증

상위 세션이 제공한 baseline 실행 요약은 Python 17개 subtest 실패와 JS 6개 feature 실패라는 의도한 red였다. 이번 문서 작업에서는 Git 원문만 읽었다. 이후 미커밋 제품 수정의 oracle 통과와 baseline 자체의 상태를 구분한다.

## 한계와 후속 개선

이 검사는 live Figma의 overflow getter·스크롤 사용성·실제 import 성공을 증명하지 않는다. 새 0.27 native 관찰은 빈 파일 읽기와 6종 폰트 calibration getter에 한정되며 이 scroll baseline의 제품 인수로 쓰지 않는다.

## 관련 기록

[674335b](674335b0a46d426723e32ab3cc98029b8b6e3744.md). 원문 대조: `git show c7a3cdef85ad0fdb7bade6a3fe5fa1e896864dd2`. 현재 기록 계약은 [Wiki 안내](../README.md)를 따른다.

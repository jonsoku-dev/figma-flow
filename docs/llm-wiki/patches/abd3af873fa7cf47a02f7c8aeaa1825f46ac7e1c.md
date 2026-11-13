<!-- patch-knowledge
{"commit":"abd3af873fa7cf47a02f7c8aeaa1825f46ac7e1c","diff_sha256":"bb397157c400c01011a39b0d77108a72f89fd20a1cbf76d851540b8de255a4ca","files":["figma-bridge/native_edit.js","figma-bridge/web_design.js","library/figma-api/coverage-baseline.json","tests/test_web_design_preview.cjs","tools/web_design.py","tools/web_design_capture.js"],"parents":["925aa87a8b7b16d7f7a7b64671bc3699933b091b"],"subject":"fix: preserve editable text tracking and render first bitmap previews","tree":"53d89e77e5c09d9b5e35d3fc48dbdb3cbb6e02d5","versions":[{"path":"plugin.json","version":"0.32.0"},{"path":".codex-plugin/plugin.json","version":"0.32.0"}]}
-->

# fix: preserve editable text tracking and render first bitmap previews

## 문제와 계기

브라우저의 제목 자간이 네이티브에 전달되지 않았고, 새 이미지 레이어는 첫 프레임 내보내기에 반영되지 않을 수 있었다.

## 결과 동작

CSSOM의 픽셀 자간을 TEXT에 쓰고 전체 텍스트 범위에서 다시 읽는다. 새 이미지 또는 실제로 선택한 영상 대체 이미지가 있는 프레임은 준비 렌더 뒤 두 번째 PNG를 반환한다.

## 변경 파일과 인터페이스

tools/web_design_capture.js, tools/web_design.py, figma-bridge/web_design.js와 figma-bridge/native_edit.js가 캡처·계획·적용·읽기를 잇는다. tests/test_web_design_preview.cjs는 재사용, 이미지 없는 화면, 영상 처리 분기를 검사한다.

## 설계 이유와 출처

자간을 별도 스타일 사본에 만들지 않고 기존 그래프 필드와 컴포넌트 식별을 사용한다. 실제 혼합값과 getter에서 얻지 못한 값을 구별한다. coverage-baseline.json에는 소스 해시만 바뀌었다.

## 호환성·이관·복구

이전 그래프와 CSS normal은 필드를 생략한다. 재사용 프레임이나 원본 영상은 불필요한 준비 렌더를 하지 않는다. 같은 프레임의 두 export는 하나의 45초 제한을 공유한다.

## 검증과 미검증

독립 Git archive 재현과 교차 출처 canvas의 첫 PNG를 비교했다. RGB(231,0,11) 13,500 픽셀이 첫 적용에 나타나며 전체 RGB는 재적용과 일치했다.

## 한계와 후속 개선

이 로직은 모든 런타임에서 실제 프레임 합성 완료를 보장하는 API가 아니다. 다른 이미지·문서의 실측을 유지해야 한다.

## 관련 기록

[측정 범위와 재현 기준](../../web-fidelity-0321.md).

원문 대조는 `git show abd3af873fa7cf47a02f7c8aeaa1825f46ac7e1c`로 한다.

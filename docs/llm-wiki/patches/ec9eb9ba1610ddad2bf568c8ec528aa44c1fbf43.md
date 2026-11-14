<!-- patch-knowledge
{"commit":"ec9eb9ba1610ddad2bf568c8ec528aa44c1fbf43","diff_sha256":"66efeef0c57f26f6805041f49367b60551095825294168596cba760739ea4775","files":["figma-bridge/web_design.js"],"parents":["6b448d99524804101f37ccf3c4283c5c70e485e4"],"subject":"fix: apply CSS opacity to SVG vector roots","tree":"b6485530c3b240f4d645b6baa8207727a8843ef6","versions":[{"path":"plugin.json","version":"0.32.1"},{"path":".codex-plugin/plugin.json","version":"0.32.1"}]}
-->

# fix: apply CSS opacity to SVG vector roots

## 문제와 계기

벡터는 일반 paint 적용을 건너뛰므로 원본의 CSS opacity도 빠졌다.

## 결과 동작

네이티브 SVG 루트에 측정한 opacity를 적용하고 내부 경로·채우기·선은 보존한다.

## 변경 파일과 인터페이스

변경 파일: `figma-bridge/web_design.js`. 전체 경로는 이 커밋 메타데이터에서 확인한다.

## 설계 이유와 출처

일반 도형의 fills 설정을 호출하면 개별 벡터의 색을 덮어쓸 수 있어 루트의 opacity만 적용한다.

## 호환성·이관·복구

포크는 이 패치 이전의 Git 객체나 설치본을 유지한 채 해당 변경을 선택적으로 적용할 수 있다. 사용자 원본과 비공개 증거는 공유 산출물에서 제외한다.

## 검증과 미검증

수정 전 동일 assertion에서 값 1을 확인하고 수정 후 기대값 0.4를 읽었다. 실제 웹 로고 검증은 다음 필터 변경과 함께 수행했다.

## 한계와 후속 개선

관찰한 입력과 환경의 결과다. 표본 이외의 파일이나 장치 및 웹 사용자 동작의 자동 복원을 보증하지 않는다.

## 관련 기록

[SVG 실측과 검증 조건](../../web-svg-fidelity-0322.md) · [이 버전의 기록](../releases.md#v0.32.2).

원문 대조는 `git show ec9eb9ba1610ddad2bf568c8ec528aa44c1fbf43`로 한다.

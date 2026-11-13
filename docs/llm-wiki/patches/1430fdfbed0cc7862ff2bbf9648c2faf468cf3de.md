<!-- patch-knowledge
{"commit":"1430fdfbed0cc7862ff2bbf9648c2faf468cf3de","diff_sha256":"4f6ffd66467b61d220852c0f01f4fe0c72d5df29adb7e7beb21adff838efbc50","files":["docs/web-design-capture.md","docs/web-fidelity-0321.md","specs/editable-web/graph.json","tests/verify_web_typography.py"],"parents":["abd3af873fa7cf47a02f7c8aeaa1825f46ac7e1c"],"subject":"test: document measured typography and verify native component reuse","tree":"50123e7e898cdaaef963b7deff1930d9913cc52b","versions":[{"path":"plugin.json","version":"0.32.0"},{"path":".codex-plugin/plugin.json","version":"0.32.0"}]}
-->

# test: document measured typography and verify native component reuse

## 문제와 계기

제목의 자간이 맞더라도 실제 컨트롤이 적절한 메인을 재사용하는지와 사용자 수정이 보호되는지는 별도 근거가 필요했다.

## 결과 동작

Portfolio와 CodeForge 제목의 브라우저 너비, 기본값 대조군, 수정 결과를 공개하고 실제 메인·인스턴스와 디자이너의 수정 상태를 검증하는 실행 경로를 제공한다.

## 변경 파일과 인터페이스

docs/web-fidelity-0321.md, docs/web-design-capture.md, specs/editable-web/graph.json 및 tests/verify_web_typography.py에서 계약과 검증을 연결한다.

## 설계 이유와 출처

포크에서 두 스타일이 무엇인지 독립적으로 지정할 수 있도록 메인·인스턴스 기대 쌍을 CLI에 전달한다. 제품의 컴포넌트 분류를 검증기에 복사하지 않는다.

## 호환성·이관·복구

비공개 원본, 화면 식별자와 PNG는 배포 패키지에 포함하지 않는다. 운영자가 자신의 그래프·읽기 영수증으로 반복할 수 있다.

## 검증과 미검증

실제 네 버튼에서 +1.5 px와 −0.75 px 메인을 하나씩 만들고 각 인스턴스가 대응 메인을 참조하는지 대조했다. Figma에서 3 px로 변경 후 changed, 복원 후 current를 읽었다.

## 한계와 후속 개선

제목 세 줄의 잔여 너비 오차는 1.45~2.83 px다. 전체 문서의 클라우드 저장 상태는 관측하지 못했다.

## 관련 기록

[편집 가능한 웹 그래프](../../../specs/editable-web/graph.json) · [실측](../../web-fidelity-0321.md).

원문 대조는 `git show 1430fdfbed0cc7862ff2bbf9648c2faf468cf3de`로 한다.

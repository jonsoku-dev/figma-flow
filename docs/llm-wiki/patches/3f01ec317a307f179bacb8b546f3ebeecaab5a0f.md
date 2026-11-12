<!-- patch-knowledge
{"commit":"3f01ec317a307f179bacb8b546f3ebeecaab5a0f","diff_sha256":"8b7a46ff3960dfac2e4ce07769c9592db6621586f7f38ad730f97a106c4c88c6","files":[".codex-plugin/plugin.json","CHANGELOG.md","README.md","docs/codex-setup-prompts.md","docs/figma-guide.md","docs/images/panel-discovery.png","docs/images/panel-graph-sync.png","docs/images/panel-import.png","docs/images/panel-review.png","docs/images/panel-workspace.png","docs/installation-and-updates.md","examples/graph-ssot/README.md","figma-bridge/README.md","figma-bridge/code.js","figma-bridge/direction_review.js","figma-bridge/graph-panel.html","figma-bridge/graph_token_sync.js","figma-bridge/panel.css","figma-bridge/ui.html","figma-bridge/workspace_chat.html","figma-bridge/workspace_chat.js","figma-bridge/workspace_home.html","figma-bridge/workspace_host.js","plugin.json","skills/figma-flow/SKILL.md","skills/figma-plugin-setup/SKILL.md","skills/graph-ssot/SKILL.md","tests/test_bridge_ui.py","tests/test_design_graph.py","tests/test_figma_bridge.py","tests/test_figma_draft.py","tests/test_figma_workspace.py","tests/test_graph_panel.cjs","tests/test_graph_sync.py","tests/test_native_render_geometry.py","tests/test_workspace_chat.cjs","tests/test_workspace_chat.py","tests/test_workspace_host.cjs","tools/design_graph.py","tools/figma_bridge.py","tools/figma_draft.py","tools/figma_workspace.py","tools/graph_sync.py","tools/plugin_panel.py","tools/workspace_chat.py"],"parents":["b1dd1d3240435d48cb9f116ca4c1654f210a340c","bf049266356987b6abbf62533a5d3b0f9c549b8b"],"subject":"Integrate unified Figma workspace with pinned skill distribution","tree":"8202e68c7174257fd61022d4c4d44bbe0de2d95e","versions":[{"path":"plugin.json","version":"0.22.0"},{"path":".codex-plugin/plugin.json","version":"0.22.0"}]}
-->
# 3f01ec3 · 통합 Figma workspace 릴리스 병합

이 기록은 원본 커밋 `3f01ec317a307f179bacb8b546f3ebeecaab5a0f`의 실제 diff와 파일 경로를 기준으로 작성했다.

## 문제와 계기

첫 부모 b1dd1d3의 0.21.1 요청 경계 수정과 두 번째 부모 bf04926의 통합 workspace 변경을 함께 배포해야 했다. merge는 workspace 구현을 릴리스 기반에 통합한다.

## 결과 동작

릴리스 통합 결과로 workspace 화면·호스트 코드, 안내 이미지·문서, 그래프 패널을 포함하면서 plugin version 및 changelog를 갱신한다. 부모 양쪽의 변경을 보존하는 merge commit이다.

## 변경 파일과 인터페이스

통합 사용자 경로는 ui.html의 탭/작업 홈과 workspace_chat/workspace_host 메시지 경계다. 요청 크기 테스트 수정은 독립적으로 보존된다.

## 설계 이유와 출처

두 부모의 변경을 일관된 배포 단위로 결합하는 릴리스 병합이다.

## 호환성·이관·복구

workspace 작업으로 전환해도 0.21.1의 서버 요청 제한 회귀 수정이 남아야 한다. 병합을 되돌릴 경우 두 부모 기능의 의존성을 함께 검토해야 한다.

## 검증과 미검증

merge diff/부모 관계는 확인했다. Figma 내 설치 실행과 실제 Codex 채팅 연결은 미검증이다.

## 한계와 후속 개선

동일 기능의 독립 merge와 달리 UI/서버 요청 경계가 함께 사용자에게 노출되므로 실제 연결 실패·중복요청 처리 확인이 필요하다.

## 관련 기록

b1dd1d3240435d48cb9f116ca4c1654f210a340c, bf049266356987b6abbf62533a5d3b0f9c549b8b, figma-bridge/ui.html, figma-bridge/workspace_host.js

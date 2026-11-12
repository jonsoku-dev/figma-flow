<!-- patch-knowledge
{"commit":"3932393cfd5cdb40edf38f0ecbc8f997cf7a9bbf","diff_sha256":"aa510aa117e4ce0bfc675730bbc54a962838bd030a70a1aa42ebf78e5dd0e9f4","files":["tests/graph_discovery_raster_oracle.cjs"],"parents":["bd511d743a228b0a71ea4a0fc5e2a92e8c0920ff"],"subject":"test: pin generated discovery raster transport","tree":"dc6533c9ccda8dbf404da7957e1351fed36e869e","versions":[{"path":"plugin.json","version":"0.26.2"},{"path":".codex-plugin/plugin.json","version":"0.26.2"}]}
-->

# test: pin generated discovery raster transport

## 문제와 계기

0.26.2의 raster table은 직접 readback과 페이지 단위 병합에서는 동작했지만, `graph_sync.py`가 Python으로 만들어 내는 별도 네이티브 discovery 번들이 이미지 테이블을 유지하는지 고정 테스트가 없었다. 실제 번들에서 여러 허용 페이지를 탐색할 때 rows는 들어와도 table 누락으로 사진 바이트를 잃는 결함을 추가로 재현했다. 구현 수정 전에 생성 경로의 oracle을 추가했다. 근거는 첫 부모 `bd511d743a228b0a71ea4a0fc5e2a92e8c0920ff` 대비 단일 테스트 파일 diff다.
## 결과 동작

테스트가 실제 `graph_sync.discovery_bundle()`로 임시 폴더에 만든 `code.js`를 읽어 VM에서 실행한다. 둘 이상의 허용 페이지에서 같은 실제 이미지 hash를 가진 네 marked IMAGE 노드가 나오면 결과의 공용 `rasterImages`에 바이트가 있어야 하고 행에는 중복 inline bytes 대신 참조가 있어야 하며 이미지 읽기는 페이지별 1회여야 한다. 이 기준 커밋의 생성 경로는 요구된 table을 전달하지 못해 oracle이 실패한다. 이 커밋은 기준 테스트만 추가한다.
## 변경 파일과 인터페이스

`tests/graph_discovery_raster_oracle.cjs`는 Python으로 discovery bundle을 생성하고 실제 생성 JavaScript의 `discoverGraphNative()`를 모형화된 Figma API로 실행한다. 기본 assertion은 실제 바이트, 4개 row 참조, inline 복제 0개, 공유 이미지의 페이지별 단일 읽기다. 제품 소스·schema·공개 함수 시그니처는 이 커밋에서 바뀌지 않는다.
## 설계 이유와 출처

소스 템플릿만 grep하는 대신 생성기가 내놓은 최종 실행 코드를 검사해 Python 생성 단계에서 누락될 수 있는 wire data를 확인한다. 같은 image hash가 서로 다른 페이지에 반복되는 조건을 사용해 각 page의 로컬 단일 읽기와 최종 bundle 병합을 모두 노출한다. 사진을 합성값으로 대체하지 않고 실행 시 실제 이미지 바이트를 공급한다. 재현 근거는 테스트의 임시 생성·VM 실행과 첫 부모 대비 diff다.
## 호환성·이관·복구

이 테스트 전용 커밋은 이미 생성된 discovery 결과, Figma 파일, 기존 readback을 바꾸지 않는다. 이 commit의 테스트 실패는 구현 전에 필요한 기준선이다. 올바른 수정은 직접 `code.js` 경로와 생성 discovery 경로 모두에서 테이블 합치기 규칙을 동일하게 적용하고, 충돌 hash의 서로 다른 바이트를 거부해야 한다. 자동 변환이나 Figma 페이지 변경은 없다.
## 검증과 미검증

기준 구현에서 이 실제 generated-bundle oracle은 실패하며, 후속 e179 수정에서 같은 고정 테스트가 통과한다. 이 커밋은 성공 결과를 포함하지 않고 테스트를 추가한 뒤의 실행 증거도 자체로 제공하지 않는다. VM 테스트는 생성 코드와 데이터 병합을 확인하지만 Figma Desktop에서 수집한 파일 전체의 시각 검토나 사용자 handoff를 증명하지 않는다.
## 한계와 후속 개선

테스트는 명시된 discovery scope 안의 두 page와 반복 해시를 대상으로 하며 대규모 페이지 목록, 네이티브 변수/스타일 전체, 브라우저 렌더링 또는 실제 Figma 권한·세션을 검사하지 않는다. byte identity는 실제 실행이 제공한 문자열과 hash별 충돌 검사에 한정된다. 최종 수정은 [생성 discovery table 보존](e179df281a870086582ad25cf649931af5a8eaa2.md)에 기록한다.
## 관련 기록

[0.26.2 직접 readback·부분 검토](bd511d743a228b0a71ea4a0fc5e2a92e8c0920ff.md), [기준 실패 오라클](ce10c8591bda9ad100c5de7a0f5323f20f5827c9.md), [수정](e179df281a870086582ad25cf649931af5a8eaa2.md), [reservation/완료 marker 결정](../decisions.md). 오라클 원문은 `git show 3932393cfd5cdb40edf38f0ecbc8f997cf7a9bbf`와 자동 메타데이터에서 확인한다.

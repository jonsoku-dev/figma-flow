<!-- patch-knowledge
{"commit":"1f90f63bfeb1fa30a4dacd311daa9720dc25ae8f","diff_sha256":"63e6dfd6a4d12ad2a1b627eb0f7b5b8417256aa2f7f41f2cb21744d4177c8e4f","files":["docs/development-roadmap/RD-03-task-dependencies/tasks.md","tools/figma_workspace.py"],"parents":["bd53b61a4da349e5857b01f5abfd47ed80e378bd"],"subject":"feat: normalize declared task dependencies before catalogue publication","tree":"2b120022ca4be2a9abc75d3e858d41104368a76c","versions":[{"path":"plugin.json","version":"0.26.3"},{"path":".codex-plugin/plugin.json","version":"0.26.3"}]}
-->
# feat: normalize declared task dependencies before catalogue publication

## 문제와 계기

기준 bd53b61a4da349e5857b01f5abfd47ed80e378bd는 dependency 정규화가 없어 `declared task dependencies must be normalized before publish`로 실패했다.

## 결과 동작

normalize_task_dependencies는 uses-output edge만 받는다. artifact는 code.js, ui.html, manifest.json 중 하나이고 hash는 선행 task의 artifact_hashes와 같아야 한다. 같은 project만으로는 edge가 생기지 않는다. 없는 target, self edge, 현재가 아닌 revision, 중복 edge, cycle은 ValueError다. publish는 서명 전에 이 검사를 호출한다. prepare의 depends_on은 새 요청 hash에 포함되어 새 revision을 만든다.

## 변경 파일과 인터페이스

tools/figma_workspace.py에 normalize_task_dependencies를 추가하고 publish와 prepare가 호출한다. docs/development-roadmap/RD-03-task-dependencies/tasks.md에 범위를 적었다. tests/test_rd03_task_dependencies.py blob은 기준과 같다. UI projection은 아직 바꾸지 않았다.

## 설계 이유와 출처

RD-03은 선행 task key, 정확한 revision, uses-output, 등록된 상대 artifact 이름과 hash만 dependency로 저장한다. 절대 경로와 추정 edge는 거절한다. DAG 검사는 전체 task 집합의 publish 경계에 둔다.

## 호환성·이관·복구

depends_on이 없는 기존 task는 필드를 추가하지 않는다. dependency 없는 prepare의 revision 계산은 이전과 같다. 실패한 cycle publish는 새 서명을 만들지 않는다.

## 검증과 미검증

종료 게이트가 기준 bd53b61a4da349e5857b01f5abfd47ed80e378bd의 종료 코드 1과 대상 1f90f63bfeb1fa30a4dacd311daa9720dc25ae8f의 종료 코드 0을 다시 실행했다. 같은 구현에서 figma workspace와 replay 검사도 통과했다. 작업 목록 UI, 브라우저, Figma 패널은 관찰하지 않았다.

## 한계와 후속 개선

edge fixture와 선행·후속 보기는 아직이다. AC의 화면 표시는 통과로 기록하지 않는다.

## 관련 기록

[실패 기준](bd53b61a4da349e5857b01f5abfd47ed80e378bd.md), [identity 경계](9c2cec203451ff81f6a0e3f83787d28c2154efca.md), [RD-03 설계서](../../development-roadmap/RD-03-task-dependencies/design.md). 원문은 git show 1f90f63bfeb1fa30a4dacd311daa9720dc25ae8f로 대조한다.

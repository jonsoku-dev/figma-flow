<!-- patch-knowledge
{"commit":"4aadf135a82d1bd4a0dde2fbdd525cfffcd93a6a","diff_sha256":"2c0f56616a9eccdeccfacaf6de8a8fc29fb19c45de1d1c4801e2c0796e5f4bc9","files":["tests/test_figma_sdk_project.py"],"parents":["42752d575ebe17ca5b10a176a29d6525719685b0"],"subject":"test: compile each shipped standalone editor recipe","tree":"ff5354f00721f70d0ab980cc4a91a3aae2510019","versions":[{"path":"plugin.json","version":"0.28.0"},{"path":".codex-plugin/plugin.json","version":"0.28.0"}]}
-->

# test: compile each shipped standalone editor recipe

## 문제와 계기

이전 컴파일 검사는 편집기별 기본 스캐폴드를 빌드했다. 배포할 실제 FigJam·Slides·Dev codegen 예제마다 strict TypeScript 컴파일이 성공하는지는 각각 확인해야 했다.

## 결과 동작

각 대상 편집기의 실제 배포 예제를 생성한 뒤 고정 컴파일러로 빌드하고 dist/code.js가 생성됐는지 검사한다.

## 변경 파일과 인터페이스

`tests/test_figma_sdk_project.py`에 `test_real_compiler_non_design_editor_recipes`를 추가했다. 테스트는 SDK의 실제 initialize 및 compile_project 함수를 거친다.

## 설계 이유와 출처

스캐폴드와 개별 예제는 서로 다른 소스를 작성한다. 예제 소스의 선언 안전성은 해당 프로젝트에서 빌드한 결과로만 확인했다.

## 호환성·이관·복구

기존 사용자는 동일한 init/check/build 명령을 사용한다. 테스트 실행 시 FIGMA_SDK_TEST_TYPESCRIPT로 설치된 TypeScript 5.9.3 경로를 전달한다.

## 검증과 미검증

고정 컴파일러로 figjam-diagram, slides-slide, dev-codegen 세 종류를 각각 생성·check·build했다. 새 CI 테스트를 직접 실행해 세 subTest 통과를 확인했다.

## 한계와 후속 개선

컴파일에는 에디터 접속과 사용자 권한이 필요하지 않다. 실제 FigJam 삽입·Slides 전환 재생·Dev Mode 코드 생성 이벤트는 이 패치의 확인 범위 밖이다.

## 관련 기록

[예제 안내](../../figma-recipes.md) · [전수 조사](../../../library/figma-api/audit/report.md) · [버전 기록](../releases.md#v0.28.0).

원문 대조는 `git show 4aadf135a82d1bd4a0dde2fbdd525cfffcd93a6a`로 한다.

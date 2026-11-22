<!-- patch-knowledge
{"commit":"bea537dd386fdd26ebeaa4d7a2a6b1a7ddbeea94","diff_sha256":"60391d71bb8dcc59f24d4693b337a12fedf6b63a893007cddc72be6f88c5b062","files":["tests/test_spec_graph_coverage.py"],"parents":["13ebd029c7d197cb7a0c6fbfbcd6cac7063a527b"],"subject":"test: require separate behavioral evidence for a criterion","tree":"9b62951328c63c47cfeaf636f944991dd48a3c6f","versions":[{"path":"plugin.json","version":"0.36.0"},{"path":".codex-plugin/plugin.json","version":"0.36.0"}]}
-->

# 구현 모듈과 인수 검사의 의미 분리

## 문제와 계기

구현과 연결된 인수 조건만으로 실제 검증을 통과한 것으로 해석하지 않아야 한다.

## 결과 동작

`bea537dd386fdd26ebeaa4d7a2a6b1a7ddbeea94`에서 코드 경로만 연결한 인수 조건과 직접 테스트를 연결한 경우를 대조한다.

## 변경 파일과 인터페이스

`tests/test_spec_graph_coverage.py`가 새 exercised-through 관계에 대한 음성·양성 예를 포함한다.

## 설계 이유와 출처

제품 코드가 있다는 사실과 성공한 검사 근거를 분리한다.

## 호환성·이관·복구

기존 checked-by 관계와 직접 요구사항 소유자를 보존한다.

## 검증과 미검증

테스트 연결이 없을 때 acceptance-no-test가 발생하고 올바른 checked-by를 추가하면 해당 오류가 사라지는 것을 확인했다.

## 한계와 후속 개선

테스트가 있다는 사실만으로 실제 사용자 인수가 완료됐음을 뜻하지 않는다.

## 관련 기록

[관계 검사기](../../../tools/spec_graph_coverage.py)

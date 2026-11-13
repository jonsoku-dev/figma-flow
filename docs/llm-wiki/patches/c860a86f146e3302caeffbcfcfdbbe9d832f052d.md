<!-- patch-knowledge
{"commit":"c860a86f146e3302caeffbcfcfdbbe9d832f052d","diff_sha256":"9fce55c8a950b46d787a85b4a767b4974a83721e2b4f750357cdcb97e9af80da","files":["tests/test_web_design_entry.py"],"parents":["4f75cb4af31947f6d4eda1f270279fa905a7c45c"],"subject":"test: pin the normal editable web-design graph entry point","tree":"788b0636465701959c394e789aba66c906fcacc3","versions":[{"path":"plugin.json","version":"0.29.0"},{"path":".codex-plugin/plugin.json","version":"0.29.0"}]}
-->

# test: pin the normal editable web-design graph entry point

## 문제와 계기

새 web-design 기능이 `native_edit.py`의 일반 public CLI에 연결됐는지 고정하는 검사가 없었다. CLI route가 사라져도 내부 helper test만으로는 이를 알 수 있었다.

## 결과 동작

`tests/test_web_design_entry.py`는 `tools/native_edit.py web-design --help`를 실행해 `--graph` option과 exit code 0을 확인한다.

## 변경 파일과 인터페이스

변경은 CLI entrypoint의 subprocess test 한 개다. Test file과 public command가 scope를 이룬다.

## 설계 이유와 출처

실제 사용자 경로를 고정하기 위해 normal CLI를 직접 실행한다. 내부 Python function 호출이나 source-string assertion으로 대체하지 않는다.

## 호환성·이관·복구

제품 command의 동작은 바꾸지 않는다. Existing commands remain unchanged; no data migration is needed.

## 검증과 미검증

0.30.0 focused web suite에서 Python 8개와 native bridge Node 4개가 통과했다. Test checks only the CLI help contract; actual plan creation and Figma import are covered by separate tests and native receipts.

## 한계와 후속 개선

Help output proves the option is advertised, not that a graph can import successfully or that a Figma write is accepted.

## 관련 기록

[native web capture guide](../../../docs/web-design-capture.md) · [native import](9eba48a5015dc991389e0c5aa3b95cd8597b5f2c.md) · [release verification](../../editable-web-verification.md#unit-checks).

원문 대조는 `git show c860a86f146e3302caeffbcfcfdbbe9d832f052d`로 한다.

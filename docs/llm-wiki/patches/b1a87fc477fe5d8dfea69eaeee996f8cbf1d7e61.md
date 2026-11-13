<!-- patch-knowledge
{"commit":"b1a87fc477fe5d8dfea69eaeee996f8cbf1d7e61","diff_sha256":"89bbaa5b0df018db08ff87b978fbfd30420501a924dc5905a90b7532175aded6","files":["tests/helpers/native_api_probe_methods.cjs","tests/native_api_probe_methods.cjs","tests/test_native_api_probe.py"],"parents":["78fd03a27d4d81d1e024d8874d5467a568b8418e"],"subject":"fix: execute the parameterized API method harness through its real caller","tree":"c82a029d68ca09d03dccf9e034536448dc94e2d5","versions":[{"path":"plugin.json","version":"0.29.0"},{"path":".codex-plugin/plugin.json","version":"0.29.0"}]}
-->

# fix: execute the parameterized API method harness through its real caller

## 문제와 계기

The API probe methods CJS file accepted arguments from its Python caller, but Node test discovery treated it as a standalone test and executed it without the required parameters.

## 결과 동작

The parameterized method harness moved under `tests/helpers/` and the actual Python caller now uses that location. Standalone `node --test tests/*.cjs` discovery no longer runs the fixture as a test file.

## 변경 파일과 인터페이스

The parameterized harness now lives at `tests/helpers/native_api_probe_methods.cjs`. Its Python caller in `tests/test_native_api_probe.py` supplies the prepared method fixture.

## 설계 이유와 출처

Moving the caller-oriented fixture under an existing helpers directory fixes the layer boundary. It preserves test coverage rather than adding a skip or successful no-op branch.

## 호환성·이관·복구

No product CLI or plugin package interface changed. Existing Python tests continue to own invocation of the fixture with pinned generated code.

## 검증과 미검증

The full local Node release suite later passed 323 tests with zero skips. The API probe also records 253 typed calls across 50 distinct members in its connected receipts.

## 한계와 후속 개선

The helper models a controlled runtime harness, not an independent live Figma UI. Native call evidence remains in the separate API receipt graph.

## 관련 기록

[API probe docs](../../../docs/native-api-probe.md) · [replay/CI evidence](../../../docs/llm-wiki/releases.md#v0.30.0) · [ranking baseline](78fd03a27d4d81d1e024d8874d5467a568b8418e.md).

원문 대조는 `git show b1a87fc477fe5d8dfea69eaeee996f8cbf1d7e61`로 한다.

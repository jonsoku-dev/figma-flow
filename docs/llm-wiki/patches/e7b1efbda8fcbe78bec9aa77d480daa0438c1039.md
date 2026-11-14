<!-- patch-knowledge
{"commit":"e7b1efbda8fcbe78bec9aa77d480daa0438c1039","diff_sha256":"b2447e98783096333b58cdea36f3785ad45ce31dbf4b072fac728d7e000cb72a","files":["tests/test_operation_detail.py","tools/operation_detail.py"],"parents":["ce1bc7d2988a7247f61cbf8fd827ed0278e0964d"],"subject":"test(control): add portable NF-03 operation detail and causal diff suite","tree":"4f94390cf7dfc0781eb1361db13d9e2b24251f9d","versions":[{"path":"plugin.json","version":"0.35.0"},{"path":".codex-plugin/plugin.json","version":"0.35.0"}]}
-->

# test(control): add portable NF-03 operation detail and causal diff suite

## 문제와 계기

`tools/operation_detail.py`의 동기화 맵 추출(`_extract_sync_map`)과 인과 diff·개인 경로 정제(redaction) 동작이 외부 로컬 환경에 의존하지 않는 포터블 회귀 테스트로 고정돼야 했다.

## 결과 동작

커밋 `e7b1efbda8fcbe78bec9aa77d480daa0438c1039`는 `tools/operation_detail.py`의 `_extract_sync_map` 처리 정확도를 보완하고, 포터블 단위 테스트 suite `tests/test_operation_detail.py`를 추가해 동일/교차 리비전 인과 diff, 선행 링크, 범위 불일치, 비공개 문자열 차단을 검증 가능하게 했다.

## 변경 파일과 인터페이스

`tools/operation_detail.py`, `tests/test_operation_detail.py`(신규)를 수정·추가했다.

## 설계 이유와 출처

실제 개인 파일시스템 경로나 비공개 키 없이 임시 디렉터리 기반 합성 아티팩트만으로 NF-03 DTO 불변식을 CI에서 반복 검증하기 위함이다.

## 호환성·이관·복구

`figma-flow-operation-detail-v1` DTO 계약과 기존 제어 라우트 시그니처를 그대로 유지한다.

## 검증과 미검증

`python3 -B -m unittest tests.test_operation_detail`이 `6/6 OK`로 통과(최신 `e6f4fd8` CI Run `43599181267`에서도 통과)했다. 이 단위 테스트는 합성 아티팩트 검증이며 실기 패널 인터랙션은 별도 Gate C 및 `e6f4fd8` HTTP 프로브로 확인했다.

## 한계와 후속 개선

런타임 패널 DOM/React 인터랙션은 `panel-ui` 빌드 환경(`esbuild`)이 있는 CI 및 `tests/test_nf03_panel_ui.cjs` 범위다.

## 관련 기록

[미배포 P1 기록](../releases.md#p1-design-acceptance) · [백엔드 구현 3e7b44c](3e7b44cc9903b3bfc753b77797e96c2c831dcd5b.md) · [인수 영수증 bf65bf0](bf65bf084304acebeb59b5d7d8aff8383d2f31e7.md)

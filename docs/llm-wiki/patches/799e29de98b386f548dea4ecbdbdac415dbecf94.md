<!-- patch-knowledge
{"commit":"799e29de98b386f548dea4ecbdbdac415dbecf94","diff_sha256":"a2020ece0e00c1d283e554bfc665ce175f8370710f78ad35e8ecab7a82597606","files":["docs/llm-wiki/catalog.json","docs/llm-wiki/patches/03ea89ed384360d3a6f7e70e4d3fa249bdc1ed93.md","docs/llm-wiki/patches/531365b4f23774444cdee1440f8756b6cd2068ff.md","docs/llm-wiki/patches/6124588d6975f572630cb72a9e5a4b8872406169.md","docs/llm-wiki/patches/6deaaf123c4f65d436fe5bb75a8f9f5711ee72f7.md","docs/llm-wiki/patches/82d765f67af47070bc787efc8dcb167c28ff2465.md","docs/llm-wiki/patches/b7c4de81869b8b5ba05bcf6a86b0707884adcecf.md","docs/llm-wiki/verification.md"],"parents":["82d765f67af47070bc787efc8dcb167c28ff2465"],"subject":"docs: record native P1 detection and graph verification scope","tree":"afefe03199a320e7d172ffa8d84edcf5d3cb7d59","versions":[{"path":"plugin.json","version":"1.0.0"},{"path":".codex-plugin/plugin.json","version":"1.0.0"}]}
-->

# P1 Design 변경 감지 결과와 확인 범위 기록

커밋 `799e29de98b386f548dea4ecbdbdac415dbecf94`

## 문제와 계기

기존 등록 작업공간에서 P1의 네이티브 콜백이 직접 opacity 편집을 전달하지 않았다. 구독 수정과 선택 값 재조회에서 확인한 사실을 과거 패치 기록과 연결할 필요가 있었다.

## 결과 동작

`docs/llm-wiki/verification.md`에 92% 편집과 100% 원복을 실제 읽기와 대화 큐 접수까지 확인한 범위를 기록했다. 예약 버튼은 편집하지 않은 상태에서 기존 정본과 읽기 값을 대조했다.

## 변경 파일과 인터페이스

`docs/llm-wiki/catalog.json`과 해당 소스 변경의 패치 페이지 여섯 개, `docs/llm-wiki/verification.md`를 갱신했다.

## 설계 이유와 출처

P1 실제 감지와 과거 증거로 수행한 별도 그래프 가져오기를 구별한다. 실제 원본 검증에서 관측한 값과 원복 기록은 제품 코드 변경의 페이지에 연결했다.

## 호환성·이관·복구

검증 기록만 갱신했다. 기존 정본의 해시와 108개 작업 키는 당시 대조 기록에 남겼다.

## 검증과 미검증

당시 P1 편집과 원복은 실제 값과 대화 큐에서 확인했다. 예약 버튼의 새 Desktop 직접 수정과 같은 회차의 그래프 반영은 확인하지 못했다고 기록했다.

## 한계와 후속 개선

이 페이지는 이전 실행의 기록 범위를 설명한다. 현재 호스트 상태와 새 편집의 동작은 해당 실행에서 다시 확인해야 한다.

## 관련 기록

[P1 검증 기록](../verification.md) · [샘플링과 그래프 검수 결합](82d765f67af47070bc787efc8dcb167c28ff2465.md)

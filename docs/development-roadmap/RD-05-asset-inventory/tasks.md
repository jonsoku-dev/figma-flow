# RD-05 작업서 · 입력 사진·글꼴·CSS 자산 목록

상태는 0.27 구현 후보이며 실제 Figma 인수는 대기다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## 구현 경로와 검증 단위

1. input-effect producer에서 prepare까지의 단일 전달 경로를 확인한다.
2. --input-record와 --input-root의 hash·source admission을 확인한다.
3. 자산 목록의 필터·복수 출처·안전한 참조를 대조한다.
4. freshness 변화, replay와 canonical 중복 제거를 확인한다.
5. CSS 간접 사진·서체의 목록과 실제 브라우저 요청을 별도로 대조한다.

아래 순서는 구현 경로와 검증 항목이다. 검사 파일의 존재나 과거 fixture 결과는 현재 실행 성공 또는 실제 Figma 인수를 뜻하지 않는다. 현재 실행 결과와 실제 관찰은 [최종 인수 기록](../FINAL_ACCEPTANCE.md)에 별도로 남긴다.

1은 `confirm_input_record_route`가 HTML 자산의 전달을 `input_effect.project`의 `html_channel`에서 `freshness`, `write_record`, `figma_workspace.prepare`의 private task artifact로 고정한다. ImportPanel은 소비자가 아니다. 현재 workspace CLI의 `--input-record`와 `--input-root`가 이 경로를 호출한다. 2는 `summarize_input_record`가 v3 record의 hash를 고정하고, 요약에는 상대 참조·종류·상태·출처·짧은 digest만 남긴다. `prepare(..., input_record=..., input_root=...)`는 그 바이트를 `input-record.json`으로 복사한다. 절대 경로와 URL query는 요약에 없고, 404·rejected·external-unverified는 present로 바뀌지 않는다. record가 없는 task에는 필드를 만들지 않는다. 3은 `assetInventory`가 문제 상태를 먼저 보여주고 상태 필터 뒤에도 상대 출처를 유지한다. 빈 목록은 모든 파일이 정상이라는 뜻이 아니다. 목록은 네트워크 요청을 하지 않는다. 4는 `fonts/body.woff2`를 `css/a.css`와 `css/b.css`가 함께 가리켜도 자산은 하나다. 그 파일 바이트가 바뀌면 이전 record의 freshness는 stale이고 changed에 `fonts/body.woff2`가 남는다. 5는 `contrast_css_browser_loading`이 같은 로컬 페이지의 목록과 승인된 브라우저에서 전달받은 relative request 관찰을 따로 남긴다. 이 함수가 브라우저를 시작하지 않는다. 쓰이지 않은 `fonts/spare.woff2`는 목록에서 present여도 브라우저 요청에 없다.

prepare는 root를 준 record의 source hashes를 준비 전후 검사하고 replay도 같은 admission을 다시 수행한다. stale 입력은 거절하고 root가 없는 record의 현재성은 unverified다. `task_input_freshness`의 결과는 exact task revision에 연결된 `inputFreshness`로 UI에 전달한다. canonical 자산 하나의 여러 CSS 출처는 `sources`로 보존한다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
python3 -B -m unittest discover -s tests -p 'test_regression_program_inputs.py'
python3 -B -m unittest discover -s tests -p 'test_input_effect_css*.py'
python3 -B -m unittest discover -s tests -p 'test_figma_workspace.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 브라우저 패널에서 missing·rejected·external·stale·empty를 확인한다. 연결 사진과 글꼴의 실제 렌더는 별도 브라우저/Figma 관찰이며 목록의 present 상태만으로 통과시키지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.

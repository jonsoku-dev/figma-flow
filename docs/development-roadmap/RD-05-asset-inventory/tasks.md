# RD-05 작업서 · 입력 사진·글꼴·CSS 자산 목록

상태는 제안이다. 우선순위는 보통이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 현재 input-effect producer에서 task까지의 전달 경로를 조사하고 한 경로를 설계서에 확정한다.
2. 한 HTML task에 hash-pinned input record를 추가하고 안전한 요약을 만든다.
3. 자산 목록과 상태별 필터·상대 출처 표시를 추가한다.
4. freshness 변화와 유입 경로 중복을 회귀 fixture로 고정한다.
5. 실제 CSS 간접 사진·서체 입력에서 목록과 브라우저 로딩을 별도 대조한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

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

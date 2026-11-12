# RD-01 작업서 · 재사용 컴포넌트와 편집 속성

상태는 제안이다. 우선순위는 높음이다. 기준과 공통 실행 계약은 [계획](../README.md), [현재 상태](../CURRENT_STATE.md), [Cursor 전달서](../CURSOR_HANDOFF.md)에 있다.

## Cursor 구현 단위

1. 현재 일반 가져오기 label 세 개 fixture와 실제 main/instance 관계를 고정한다.
2. TEXT property 생성·참조·instance.setProperties를 한 경로에서 구현하고 기존 코드 경로를 교체한다.
3. 재실행과 사용자 override 보존을 확인한 뒤 첫 단위를 닫는다.
4. 크기 차이만 있는 fixture와 구조 차이 fixture로 재사용 분류를 별도 구현한다.
5. 독립 축이 필요한 실제 입력을 먼저 등록하고 variant_axes·사용 설명을 마지막 단위로 추가한다.

한 단위가 완료되면 실제 diff와 인수 조건을 대조하고 다음 단위로 진행한다. 새 schema·UI만 추가한 채 소비자를 남겨 두지 않는다. 다른 항목을 같은 변경에 넣지 않는다.

## 기존 검사에서 시작하기

저장소 루트에서 실행한다. 아래 경로는 현재 존재하는 검사다. 새 동작의 회귀는 관련 파일에 추가하거나 책임이 분명한 새 파일을 만든다. 기존 검사가 새 기능을 이미 검증한다고 간주하지 않는다.

```sh
node --test tests/test_graph_token_sync.cjs tests/test_native_control_icons.cjs tests/test_native_control_alignment.cjs
python3 -B -m unittest discover -s tests -p 'test_design_system.py'
python3 -B -m unittest discover -s tests -p 'test_design_foundations.py'
```

React를 바꾸면 `npm --prefix panel-ui run build`를 실행하고 원본과 생성 자산을 함께 검수한다. 영향받지 않은 테스트와 검증 근거는 재사용하되 소스 revision을 명시한다.

## 실제 동작 확인

실제 Figma에서 property 패널의 문구 변경, main 수정의 여러 instance 반영, resize, 재실행을 관찰한다. 소유 fixture 외 main이나 instance는 변경하지 않는다.

## 완료 조건과 반환

[기능서](feature.md)의 모든 해당 AC에 구현·자동 검사·실제 관찰 또는 미검증 이유를 연결한다. 변경 파일, 실행 명령과 결과, 호환성, 남은 위험, CHANGELOG와 상세 Wiki 경로를 [공통 반환 형식](../CURSOR_HANDOFF.md#작업-결과-형식)으로 남긴다. 실제 관찰이 빠졌으면 해당 AC를 통과로 바꾸지 않는다.

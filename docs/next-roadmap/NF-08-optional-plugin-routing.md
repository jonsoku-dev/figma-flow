# NF-08 선택적 설치 plugin 경로

상태는 **PROPOSED**다. G0~G5, native read/design-to-code, web import, component families, causal history/accessibility, large-document work, editor capability matrix를 각각 인수한 뒤 검토할 선택 기능이다. 공식 plugin 연동 없이도 Figma Flow의 핵심 경로를 쓸 수 있어야 한다.

## 기능 계약

사용자가 특정 공식 Figma plugin이 제공하는 기능을 요청하면 Figma Flow가 검토된 경로를 안내할 수 있다. 경로에는 plugin 이름·publisher, 필요한 editor/mode, 지원 task, handoff data가 표시된다. 사용자는 Figma 안에서 plugin을 열고 쓰기 동작을 직접 확인한다.

이 기능은 plugin을 설치·업데이트하거나 몰래 실행하지 않는다. 인증·권한 부여·파일 선택·쓰기·실행 결과 성공 표시도 하지 않는다. 신뢰할 수 있는 설치 여부, handoff 지원, plugin capability 중 하나라도 모르면 기존 local/native 경로를 안내한다. 임의 요청이나 프로젝트 전체 내용을 외부 plugin으로 전달하지 않는다.

## 시작 조건과 데이터

구현 전에 사용자가 정확한 공식 plugin과 기능을 지정해야 한다. 공식 source로 publisher를 확인하고, 필요한 editor/mode, 기능, handoff 계약과 사용 범위를 기록한다. 앞선 핵심 우선순위의 인수 결과도 있어야 한다. Figma host가 설치 plugin을 신뢰성 있게 제공하지 않으면 사용자가 UI에서 확인하는 단계를 둔다. 문서화되지 않은 local file이나 private API로 설치를 추측하지 않는다.

선택 route record는 안정 ID, 표시 이름, 공식 publisher/source, editor와 mode, capability ID, 넘길 data field, 한계, 마지막 검증 evidence를 저장한다. 이 제안은 현재 어떤 plugin ID나 공식 route도 확정하지 않는다. Figma Flow manifest에 해당 plugin 의존성을 추가하지 않는다.

Router 결과 상태는 `available`, `user-confirmed`, `unavailable`과 evidence, 다음 행동이다. package 이름이나 문서만 보고 `installed`를 반환하지 않는다. Handoff field는 allowlist와 명시적 크기 상한을 사용한다. Raw native readback, credentials, private URL, 관련 없는 project data는 제외한다.

## 인터페이스와 구현 경계

`tools/figma_feature.py`에 read-only, versioned optional route registry만 추가한다. 기본 local route를 먼저 보여준다. Optional route는 사용자가 선택하고 availability evidence가 유효할 때만 제공한다. 신뢰할 수 있는 설치 검사가 없으면 사용자에게 확인을 요청하고 일반 Figma UI 절차를 안내한다. 문서화되지 않은 plugin manager API를 호출하거나 두 번째 실행 bridge를 만들지 않는다.

첫 버전은 안내와 제한된 data export다. 자동 plugin launch나 native mutation은 없다. 문서화된 Figma API가 안정된 user-approved handoff를 제공하고 정확한 plugin이 현재 host에서 사용 가능하다고 확인한 뒤에만 launch 지원을 별도 proposal로 검토한다.

## 검증과 rollback

Absent plugin, unknown availability, user confirmation, editor mismatch, unsupported capability, 오래된 evidence, 과대 handoff, redaction을 검사한다. 모든 route 결과가 `execution: not-executed`인지 확인한다. Optional route 조건이 없을 때 기존 local route step은 byte-for-byte 같아야 한다.

실제 Figma 검사 전에 사용자가 plugin, 정확한 file/page, handoff field, 쓰기 여부를 정해야 한다. Figma UI에서 plugin identity를 확인하고, 전송 전 data를 검사한 뒤 작은 task 하나만 실행한다. 결과는 기존 full native reader로 다시 읽는다. 실제 plugin availability와 공식 문서 근거는 따로 기록한다. Mock은 installed plugin 증거가 아니다.

Rollback은 optional route record와 생성된 reference 항목을 지운다. 기존 local routing은 유지한다. 미래 handoff가 쓰기를 하게 되면 exact before-state, owned-node 목록, 조건부 rollback도 자체 계약으로 둔다. plugin이 소유권과 값을 읽는 경로를 제공하지 않으면 복구를 약속하지 않는다.

정확한 plugin을 선택한 후 실행할 검사 제안은 다음과 같다.

```sh
python3 -B -m unittest discover -s tests -p 'test_figma_feature.py'
python3 -B -m unittest discover -s tests -p 'test_editor_capabilities.py'
```

새 `test_editor_capabilities.py`는 아직 제안이다. 기본 local route 불변, optional route 선택, evidence 만료, scope 유지, non-execution을 검사한다. 실제 plugin 동작은 별도의 사용자 승인 Figma 인수가 필요하다.

Cursor 구현 프롬프트:

```text
앞선 roadmap 우선순위에 acceptance evidence가 있고 사용자가 정확한 공식 plugin을 지정하기 전에는 NF-08을 구현하지 않는다. 공식 identity, publisher, capability, editor mode, 문서화된 availability signal을 먼저 확인하라. 설치 여부를 공식 API로 읽을 수 없으면 사용자 확인을 요구하라. Read-only optional route registry와 제한된 검토용 handoff 안내만 구현한다. 모든 local route를 fallback으로 보존하라. Install, launch, auth, permission grant, file 선택, data send, plugin 실행, native 성공 주장은 금지한다. 기본 route 동일성, unknown/unavailable, stale evidence, capability mismatch, redaction, non-execution 검사를 추가하라. 실제 Figma 동작은 사용자가 정한 정확한 범위에서만 수행한다. route 계약, provenance, 집중 검사 결과, runtime 미검증 한계를 반환하라.
```

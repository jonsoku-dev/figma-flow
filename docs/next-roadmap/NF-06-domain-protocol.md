# NF-06 도메인 경계와 버전 전환

상태는 **PROPOSED**다. RD-07의 전송 모듈 분리는 이미 구현되어 있다. 이번 범위는 정책의 단일 소유와 명시적인 호환 프로토콜이다.

## 기능 계약

사용자는 오래 준비한 task와 새 플러그인 런타임이 섞였을 때 불명확한 실패 대신 "재준비 필요"와 정확한 비호환 범위를 보고 싶다. 유지보수자는 workspace 준비·발행·입력 admission·control lifecycle의 변경이 다른 경로의 보안 검사를 조용히 바꾸지 않게 하고 싶다.

결과는 각 도메인 정책의 소유 모듈과 버전 handshake다. 기계적인 파일 분리만으로 완료하지 않는다. 새 서버·DB·RPC framework·event bus·LangGraph는 도입하지 않는다. 불확실한 operation을 자동 재전송하지 않는다.

## 현재 경로와 확장 위치

`tools/figma_workspace.py`는 `private_dir`, `locked`, `current`, `trusted_sources`, `assemble_shared_runtime`, `publish`, `prepare`, `normalize_task_dependencies`, `task_input_record`, `task_input_freshness`를 함께 소유한다. 실제 보안·CAS·출처 검증을 이동 중 빠뜨리지 않는다.

`tools/figma_control.py`의 `require_ready`, `enqueue`, `poll`, `note_native_started`, `result`, `history`는 canonical phase와 불확실 쓰기 차단을 맡는다. `figma-bridge/workspace_transport.js`는 loopback·size·15초 deadline만 처리하며 `workspace_control.js`는 operation admission을 유지한다. `tests/fixtures/rd07/protocol-trace.json`은 현재 routes/allowed/source pins 기준이다. 이것을 새 버전 지원을 핑계로 지우거나 느슨하게 만들지 않는다.

## 모듈과 인터페이스 제안

Python의 목표 의존 방향은 `workspace CLI → domain functions → private storage helpers`다. control은 public workspace domain interface를 호출한다. publisher는 control phase를 추정하지 않고 발행 가능 여부를 조회한다. 입력 admission은 prepared artifact의 hash·source root·revision만 반환하고 publish나 native 실행을 하지 않는다.

| 제안 모듈 | 소유 정책 | 외부로 내보낼 최소 함수 |
| --- | --- | --- |
| `tools/workspace_storage.py` | private 파일·경로·lock·atomic write | 기존 의미를 보존한 read/atomic/locked/private_dir |
| `tools/workspace_admission.py` | source pins·input record·dependency artifact admission | validate_prepared_inputs, input_freshness, normalize_dependencies |
| `tools/workspace_publisher.py` | trusted runtime 조립·catalogue 발행 | assemble_runtime, publish_catalogue |
| `tools/figma_workspace.py` | CLI orchestration·prepare/replay | 현재 public CLI와 최소 domain entrypoint |
| `tools/figma_control.py` | control scope·phase·uncertainty | 현재 public control entrypoint와 typed compatibility result |

함수 이름은 제안이다. 실제 caller 목록을 추적해 한 번에 하나의 경계를 옮긴다. storage는 domain module을 import하지 않는다. publisher/admission 간 순환 호출을 만들지 않는다. 현재 호출자가 쓰는 공개 함수는 직접 re-export하거나 같은 의미의 얇은 entrypoint로 한 이행 단계만 유지한다. 저장 형식까지 동시에 바꾸지 않는다.

JS는 현재 전송/정책 경계를 유지한다. task 종류별 adapter는 실제 분기가 독립적으로 테스트 가능한 경우에만 분리한다. 모듈 수 증가 자체는 인수 조건이 아니다. trusted source 목록과 source fingerprint에 새 module이 포함되는지 실제 조립 검사로 확인한다.

## 프로토콜과 상태 전환 설계

현재 runtime fingerprint 검사에 선택적 `protocol` envelope를 더한다. 제안 필드는 `{major, minor, capabilities}`다. capability는 임의 문자열 권한이 아니라 고정 목록의 기능 지원 정보다. operation admission은 기존 allowlist·exact scope·revision·deadline·claim을 계속 확인한다.

초기 capability 예시는 `history-detail-v1`, `summary-browse-v1`, `web-artifacts-v1`다. 해당 패킷이 구현·검증되기 전에는 광고하지 않는다. handshake 결과는 `compatible`, `legacy-read-only`, `reprepare-required`, `unsupported-major`, `unknown`이다. 서버와 native가 같은 major이며 필요한 capability를 모두 제공할 때만 새 경로를 허용한다. minor 숫자만 보고 기능 지원을 추정하지 않는다.

field 없는 구버전은 현재 legacy 동작으로 읽되 새로운 capability 경로는 닫는다. 기존 호환 policy를 완화하지 않는다. 이미 exact runtime 불일치를 거절하는 곳은 새 envelope로 우회하지 않는다. malformed/unknown major와 필수 capability 누락은 native-started 이전에 거절한다. 실행 중 준비 번들이 교체되면 기존 command를 재생하지 않는다.

## 화면·오류·보안·접근성

Workspace는 현재 준비 버전·관측 native 버전·비호환 이유를 나란히 표시하고 **작업 다시 준비 안내**를 제공한다. 버튼은 준비 명령 안내를 열며 임의 재실행·재설치를 하지 않는다. 상태는 checking, ready, reprepare-required, incompatible, unavailable다. phase unknown·uncertain operation은 별도 표시하며 버전 오류로 지우지 않는다.

JSON 오류는 stable reason code, expected/observed protocol 범위, 안전한 다음 행동으로 구성한다. bearer·claim secret·private 설치 경로는 메시지에 넣지 않는다. support capability가 native 실행 권한이나 계정 승인이 되지 않는다. 라이브 상태는 과도한 반복 없이 보조 기술에 전달하고 focus를 자동으로 빼앗지 않는다. 좁은 화면에서도 버전 값과 동작을 읽을 수 있어야 한다.

## 마이그레이션·rollback 계약

1. 현재 protocol trace·domain public callers·golden catalogue를 읽기 fixture로 고정한다. 새로운 기준이 필요하면 커밋 권한 소유자가 별도 기준을 먼저 보존한다. 구현 diff로 기존 독립 검사 기준을 수정하지 않는다.
2. 모듈 이동은 저장 bytes·phase·HTTP 경로·부작용 순서를 그대로 유지하는 독립 단위로 한다. 공개 CLI와 기존 caller를 먼저 이행한다.
3. envelope parsing을 읽기 전용으로 추가하고 old/new 조합을 검사한다. 이 단계에서는 새 capability를 광고하지 않는다.
4. 필요한 capability가 검증된 endpoint만 opt-in한다. 저장 catalogue schema가 달라지면 새 version으로 쓰고 구버전 reader가 파괴하지 않도록 별도 파일/변환 경로를 둔다.
5. rollback 시 이전 runtime/catalogue 쌍을 복원한다. 새 envelope가 없는 이전 작업은 재준비 안내로 처리한다. 실행 중·uncertain operation의 journal을 삭제하거나 재작성하지 않는다.

## 작은 작업과 한 writer 경계

1. `tools/figma_workspace.py`, 새 `tools/workspace_storage.py`, 새 `tools/workspace_admission.py`, 새 `tools/workspace_publisher.py`, 새 `tests/test_workspace_domains.py`는 한 소유자가 순차 수정한다. public callers를 rg로 먼저 기록한다.
2. `tools/figma_control.py`, 새 `tests/test_protocol_compatibility.py` 소유자가 새 envelope 읽기와 reason codes를 추가한다. 1번의 domain interface가 확정된 뒤 시작한다.
3. `figma-bridge/workspace_host.js`, `figma-bridge/workspace_control.js`, `figma-bridge/workspace_transport.js`, 새 `tests/nf06_protocol_compatibility.cjs` 소유자가 native handshake를 연결한다.
4. `panel-ui/src/Workspace.jsx`, `figma-bridge/locales/workspace.json`, `panel-ui/src/styles/workspace.css` 소유자가 재준비 안내를 붙인다. NF-03과 같은 파일을 동시에 쓰지 않는다.
5. 통합 담당자가 publisher의 trusted module/source pins·legacy/new 번들·중단 operation 보존을 실제 생성 번들로 검증하고 필요한 생성 자산·패치 기록을 갱신한다.

## 인수와 검증

```sh
python3 -B -m unittest discover -s tests -p 'test_figma_workspace.py'
python3 -B -m unittest discover -s tests -p 'test_workspace_publish_guard.py'
python3 -B -m unittest discover -s tests -p 'test_rd07_*.py'
python3 -B -m unittest discover -s tests -p 'test_rd08_*.py'
node --test tests/test_workspace_control.cjs tests/test_workspace_host.cjs tests/test_native_runtime_version.cjs
npm --prefix panel-ui run build
```

새 검사 제안은 `python3 -B -m unittest discover -s tests -p 'test_workspace_domains.py'`, `python3 -B -m unittest discover -s tests -p 'test_protocol_compatibility.py'`, `node --test tests/nf06_protocol_compatibility.cjs`다. import 순환 부재, trusted module tamper, identical catalogue/output, private path·lock·CAS 유지, old/new 조합, missing/unknown capability, 거절 후 native-started 부재를 검사한다. 실제 플러그인에서 일치 쌍은 정상 동작하고 불일치 쌍은 실행 전에 안내해야 한다. 모듈 분리로 평균 시간이 좋아졌다고 추정하지 않는다. 기존 준비/실행 동일 작업을 비교해 성능 퇴행 여부만 확인한다.

## Cursor 구현·테스트 프롬프트

```text
NF-06만 구현하라. RD-07 전송 분리는 이미 끝났으므로 반복하지 말라. 현재 figma_workspace의 public callers, publisher/trusted_sources/input admission과 figma_control phase/uncertainty를 먼저 추적하라. 소유 범위는 작업 1~4와 필요한 생성 자산·패치 기록이다. Python domain 추출은 한 writer가 순차 실행하고 다른 dirty 작업을 보존하라. 우선 behavior-preserving 경계 이동, 그다음 optional protocol parsing, 마지막 검증된 capability 광고 순서다. 저장 bytes·부작용·보안 검사·public CLI를 유지하고 minor 숫자로 권한을 추정하지 말라. 기존 독립 검사/trace 기준을 구현 diff에서 낮추지 말라. 새로운 runtime/dependency/DB/프로토콜 우회/불확실 쓰기 재실행/게시·커밋을 금지한다. 기존 명령·새 독립 검사·실제 생성 번들 old/new 호환 검사를 수행하라. 기준 변경이나 소유 밖 변경이 필요하면 해당 mutation을 멈추고 이유를 보고하라. 반환은 파일/의존 방향, 호환 매트릭스, 보안·회귀 결과, 실제 runtime 근거, rollback과 미검증 위험이다.
```

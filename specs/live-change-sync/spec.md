# 현재 Design 변경의 그래프 동기화

현재 열려 있는 Figma Design 페이지에서 받은 변경 메타데이터를 기록하고, 서명된 작업으로 현재 값을 다시 읽어 정본 그래프와 비교한다. 사용자가 요청한 경우에만 변경 없는 그래프·웹 pairing을 확인하고 지원되는 값만 로컬 파일에 적용한다. [기능 그래프](graph.json)

## 범위와 사전 조건

사용자가 Codex에 **“현재 열린 Figma Design 페이지 변경을 감시해. 제한된 세부 정보와 그래프 미리보기를 알려 주고 적용은 하지 마.”**처럼 요청한다. 적용을 원하면 **“현재 페이지에서 관측한 변경 중 정본 그래프와 웹 pairing에 정확히 연결되고 미지원 차이가 없는 값만 로컬 graph와 web에 반영해.”**처럼 별도로 요청한다.

`figma_control.py serve`와 `figma_follow.py` watcher가 같은 비공개 workspace에서 실행 중이어야 한다. 등록된 Figma Flow 플러그인이 요청한 파일·페이지를 현재 문맥으로 열고 listener를 보고해야 변경 이벤트가 도착한다. 연결이 끊기거나 listener를 사용할 수 없으면 watcher는 `offline` 또는 `listener-unavailable` 상태를 기록하고 자동 적용을 막는다. watcher는 파일·페이지·런타임 세션에 묶인 커서를 사용한다.

Figma 이벤트는 노드 ID, 변경 종류, 속성 이름, 순서와 제한된 origin 값만 기록한다. 변경을 수행한 계정·사람은 식별하지 않으며 `origin: unknown`을 사람의 편집이라고 추정하지 않는다. `figma-flow-plugin` origin 이벤트는 journal에 남지만 watcher의 외부 변경 알림과 preview 입력에서 제외한다.

## 요구사항

- `REQ-LIVE-01` — 현재 활성 파일·페이지의 변경 메타데이터를 private journal에 커서와 함께 보존한다. 중복 이벤트는 제한된 짧은 구간으로 묶고, 수신 공백과 listener 상태를 별도 표시한다.
- `REQ-LIVE-02` — `--inspect-task`와 `--inspect-revision`은 같은 파일·페이지의 고정된 `discover` 작업을 요구한다. 이벤트 노드의 현재 속성은 제한된 `selection-info` 읽기로 확인한다. `--read-task`와 `--revision`은 별도로 고정된 `discover` 또는 `sync` 읽기로 전체 현재 상태를 가져와 그래프 pairing과 비교한다.
- `REQ-LIVE-03` — 기본 동작은 로컬 event receipt와 graph preview를 만든다. `--apply-clean`은 변경 이벤트의 노드·속성 증거가 preview에 연결되고, 수신 공백이 없고, 지원되지 않는 변경과 binding repair가 없고, pairing의 graph와 web hash가 현재 파일과 일치할 때만 graph와 web module을 갱신한다. 적용 후에도 pairing baseline은 갱신하지 않는다.
- `REQ-LIVE-04` — `--notify-current-chat`은 현재 Codex thread에 변경 수와 허용된 속성 이름, 로컬 receipt 경로만 queue한다. Figma 노드 이름과 텍스트 내용은 채팅 알림에 넣지 않는다. `--resume-chat`은 선택적으로 local Codex daemon에 재개를 요청한다.
- `REQ-LIVE-05` — 하나의 watcher만 해당 `--state-dir`에서 실행한다. `latest`는 최근 읽은 노드 값을 제한된 수로 보여준다. `status`는 lock을 확인해 `running` 또는 `stopped`를 보고한다. `stop`은 같은 실행 instance에 stop 요청을 남기고 watcher가 이를 확인한 뒤 종료한다.

## 인수 조건

- `AC-LIVE-01` — watcher는 현재 listener가 보고하는 파일·페이지 scope만 받는다. scope가 바뀌거나 플러그인이 오프라인이면 새 scope의 커서를 다시 시작하고 누락 구간을 표시한다.
- `AC-LIVE-02` — 정확한 task revision이 파일·페이지·허용 작업 종류와 일치하지 않으면 읽기를 거부한다. `--inspect-task`는 최대 20개 노드 ID와 `INSPECT_FIELDS`에 등록된 필드만 요청한다. `characters`는 `--include-text`를 지정한 경우에만 읽는다. 변경 속성 중 지원하지 않는 필드는 unsupported로 기록한다.
- `AC-LIVE-03` — `--read-task`의 private readback과 graph preview는 event metadata와 구분한다. event는 이전 값이나 변경 수행자를 입증하지 않는다. 전체 readback은 읽는 시점의 현재 상태이며 이벤트 직후 추가 변경을 포함할 수 있다.
- `AC-LIVE-04` — `--apply-clean`은 매핑된 변경 노드·속성 증거가 있는 graph update만 적용한다. gap, offline 상태, 미지원 변경, binding repair, 불일치 graph hash, 불일치 web module hash 또는 변경 증거가 없는 update가 하나라도 있으면 `review-required`로 끝나고 graph와 web을 보존한다. 성공해도 pairing은 `pairing_advanced: false`다. 적용 대상은 로컬 graph와 web module이며 Figma에는 쓰지 않는다.
- `AC-LIVE-05` — 알림 대상은 `CODEX_THREAD_ID`에 들어 있는 UUID와 `codex queue --thread`다. `queued`는 queue 명령의 접수를 뜻한다. `consumed: false` 상태를 유지하며 모델이 메시지를 읽거나 처리했다고 표시하지 않는다. queue 결과가 불확실하면 같은 batch를 자동 재전송하지 않는다.
- `AC-LIVE-06` — `--resume-chat`은 `--notify-current-chat`과 함께만 허용한다. current-chat 알림을 쓰려면 해당 Codex thread에서 local `codex` queue 명령을 실행할 수 있어야 한다. 알림은 webhook, Figma 계정 작업 또는 Figma 내용의 모델 프롬프트 삽입을 사용하지 않는다.
- `AC-LIVE-07` — `status`와 `stop`은 실행 시작 시 사용한 것과 같은 `--state-dir`에서 읽는다. `stop-requested`는 종료 완료가 아니며, lock이 풀린 뒤 `stopped`를 확인한다.
- `AC-LIVE-08` — `latest`는 최대 256개 노드의 직전 native read 값을 저장한다. `--node-id`는 한 노드로 결과를 제한한다. 노드가 cache에 없으면 값을 관측하지 않은 상태로 표시하고 새 읽기를 요구한다. gap 또는 cursor epoch 변경은 이전 cache를 비운다. gap batch의 노드 세부 읽기가 성공한 경우에만 새 값으로 다시 채운다.

## 필드 및 전달 한계

Plugin listener는 `nodechange`에서 변경 종류와 속성 이름을 기록한다. 이벤트에는 노드 텍스트나 속성 값이 없다. 한 batch의 이벤트 수는 bounded이며 노드 세부 읽기는 최대 20개다. 세부 읽기는 현재 정책의 `INSPECT_FIELDS`만 요청한다. 지원 필드는 이름, 텍스트, 표시·불투명도, 위치·크기·회전, 모서리, padding·layout·spacing, 글꼴, fill과 stroke다. `characters`는 명시적 text opt-in이다. 모르는 속성 이름은 지원되는 값으로 추정하지 않는다.

현재 listener는 80ms 타이머 뒤 batch당 최대 64개 이벤트를 전송하고, 이벤트 하나에는 최대 32개 속성 이름을 기록한다. 속성 목록이 잘리면 `properties_truncated`를 남긴다. 노드 세부 읽기는 최대 20개다. watcher는 짧은 편집 묶음을 위해 약 350ms 기다린다. 이는 현재 구현의 관측 가능한 batching 동작이며 subsecond 알림 또는 지속 실행 SLA가 아니다. OS 절전, 플러그인 닫힘, Desktop 연결, local daemon 처리 시간은 보장하지 않는다.

## 실제 로컬 관찰

한 private Design 실행에서 opacity를 100%에서 92%로 바꾼 이벤트와 92%에서 100%로 되돌린 이벤트를 각각 약 0.56초 뒤 기록했다. 자동 세부 읽기에는 복원된 값 `1.0`이 나타났다. 이는 한 실행의 관찰값이며 전달 시간 SLA가 아니다.

한 번의 임시 idle Codex thread에서는 `--notify-current-chat --resume-chat`으로 queue한 메시지 뒤 thread가 재개되어 완료됐다. 바쁜 현재 thread에서는 알림이 queue됐지만 현재 실행을 빼앗지 않았다. queue 접수와 모델이 알림을 실제로 소비한 상태는 계속 별도다.

`--state-dir`의 event receipt, `details`, `readback`, `graph-preview`는 각각 관측 메타데이터, 세부 읽기, 읽은 시점의 현재 상태, 로컬 비교 제안이다. 서로를 Figma 원본의 완전한 diff나 사람의 승인으로 해석하지 않는다. 완료·적용 결과는 Codex가 각 receipt를 확인한 뒤 별도로 보고한다.

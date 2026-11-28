# PC 로컬 메트릭 노출 및 외부 수집 연계

Figma Flow의 선택적(opt-in) 메트릭과 headless 진단 기능 계약을 정의한다. Figma 플러그인의 `networkAccess.allowedDomains: ["none"]` 경계와 수동 뷰어 원칙을 바꾸지 않고, 사용자 PC에서 실행되는 `figma_control.py` 로컬 허브와 어댑터 계층(`tools/metrics/`)에서 모든 수집·필터링·노출·전송을 처리한다. [기능 그래프](graph.json)

## 범위와 설계 원칙

- **전부 옵셔널(No-op 기본값):** PC 설정 파일(`$WORKSPACE/metrics.json` 또는 `~/.config/figma-flow/metrics.json`)이 없거나 `enabled: false`이면 `NullRecorder`로 동작하며, 외부 전송·네트워크 호출·작업공간 파일 생성·`/metrics*` 엔드포인트 노출이 전혀 없다.
- **양방향 어댑터(Ports & Adapters):** 수집 소스(`operations`, `live_changes`, `workspace`, `quality`, `benchmark`), Pull 포맷(`prometheus`, `json`), Push 싱크(`http-json`, `otlp-http`, `jsonl-file`, `statsd-udp`)가 각각 독립 포트(`SourceAdapter`, `PullAdapter`, `PushSinkAdapter`)를 구현한다.
- **Computer Use 없는 Headless 운영:** `figma_control.py metrics` CLI로 설정·테스트·스냅샷·즉시 플러시(`flush`)·진단(`doctor`)·준비 대기(`watch --until-ready`)를 비대화형 JSON/NDJSON으로 수행하고, `figma_flow_plugin_online`·`figma_flow_plugin_last_seen_age_seconds`·`figma_flow_plugin_runtime_current`·`figma_flow_uncertain_operations`·`figma_flow_active_operation_age_seconds`·`figma_flow_profile_needs_setup` 실시간 게이지로 플러그인 상태를 원격·헤드리스 환경에서도 판별한다.

## 요구사항

- `REQ-METRIC-01` — 기본 비활성(`NullRecorder`) 상태에서 기존 `/control/*` 엔드포인트·`readiness()`·작업공간 파일에 부작용을 남기지 않는다.
- `REQ-METRIC-02` — 소스 어댑터, Pull 어댑터, Push 싱크 어댑터를 레지스트리 포트로 분리해 새 외부 수집기나 소스를 코어 수정 없이 확장할 수 있다.
- `REQ-METRIC-03` — PC별 로컬 계층 설정(`~/.config/figma-flow/metrics.json` 기본값 + `$WORKSPACE/metrics.json` 우선 덮어쓰기)을 `0600` 소유자 전용 권한과 환경변수/파일 비밀키 참조(`${ENV_VAR}`, `file:/path`)로 관리하고 동적으로 재적용한다.
- `REQ-METRIC-04` — 장애 격리(Fail-open)된 싱크별 bounded 큐·재시도·서킷브레이커로 외부 API 장애나 타임아웃이 Figma 제어 흐름을 지연·차단하지 않게 한다.
- `REQ-METRIC-05` — Computer Use 없이 CLI(`init`, `enable`, `disable`, `add-sink`, `test`, `snapshot`, `flush`, `doctor`, `watch`)와 기능 라우터(`figma_feature.py`), 실시간 게이지로 플러그인 연결·런타임 일치·차단 상태를 진단하고 대기한다.

## 인수 조건

- `AC-METRIC-01` — 설정이 없거나 비활성일 때 `/metrics`와 `/metrics/json`은 `404`를 반환하고, `readiness()` 및 `/control/*` 스냅샷과 호환된다.
- `AC-METRIC-02` — `strict`(기본)·`hashed`·`scoped` 프라이버시 모드에 따라 `file_key`·`page_id`·`task_key`·`user_id` 및 토큰/홈 경로를 차단·해시·허용하며, 비밀키 원문은 진단·테스트·오류 응답에 절대 노출하지 않는다.
- `AC-METRIC-03` — Pull 어댑터(`prometheus`, `json`)가 `control-token`, `bearer-secret`, `none` 인증 정책을 따르고 실시간 헤드리스 게이지와 카운터/히스토그램을 렌더링한다.
- `AC-METRIC-04` — Push 싱크 어댑터(`http-json` 매핑 포함, `otlp-http`, `jsonl-file` 회전, `statsd-udp` DogStatsD 태그 포함)가 `include_sources`/`exclude_metrics` 라우팅 및 HTTPS 강제(localhost 예외)를 준수해 전송한다.
- `AC-METRIC-05` — 외부 수집기가 다운·느림 상태이거나 큐가 가득 차도 제어 `poll`/`result`는 정상 성공하며 `figma_flow_metrics_queue_dropped_total`·`sink_health`에 상태가 기록된다.
- `AC-METRIC-06` — `metrics doctor`·`watch --until-ready`·`flush`·`snapshot`·`test`와 `POST /metrics/ingest`·`POST /metrics/flush`가 `serve` 온라인·오프라인 정책에 따라 동작하고, 읽기 전용 게이지 수집이 작업공간 파일을 변경하지 않는다.

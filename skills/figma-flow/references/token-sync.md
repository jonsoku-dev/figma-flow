# Figma 재읽기에서 앱까지: 오프라인 토큰 변경

0.9.0은 기존 0.8.0 설정을 유지하며 `tools/serve_figma_sync.py`로 Figma의 **앱에 반영** 버튼을 로컬 앱에 연결한다. 수동 JSON 계획·적용은 기존 `tools/apply_figma_change.py`를 유지한다. Figma Desktop 개발 플러그인에서 내보낸 변경 전·후 JSON을 로컬에서 비교하고, 선택한 가져오기 페이지의 스칼라 토큰 값을 앱으로 반영한다. Figma MCP·원격 연결 검사는 호출하지 않는다. 사용자가 허용한 Figma 파일에서 가져오기·편집·내보내기를 수행한다. 로컬 입력의 구조·해시·동일성 검사는 JSON의 실제 Figma 출처를 인증하지 않는다.

## 버튼 한 번으로 반영하기: 0.8.0

앱 프로젝트, 처음 가져올 때 사용한 `ORIGINAL_RESOLVED`, 실제 Figma 파일 키·가져오기 페이지 ID와 본인에게 발급된 숫자 플러그인 ID를 준비한다. 상태 폴더는 앱 프로젝트 밖의 전용 비공개 폴더다. 플러그인 루트에서 다음을 실행하고 도우미를 계속 켜 둔다. `2:77`은 예시이므로 실제 페이지 ID로 바꾼다.

```sh
python3 tools/serve_figma_sync.py --project PROJECT --resolved ORIGINAL_RESOLVED --page-id 2:77 --file-key FILE_KEY --plugin-id FIGMA_ID --state-dir PRIVATE_DIR [--prior-sync PRIOR_0_7_APPLIED]
```

1. 출력된 `PRIVATE_DIR/plugin/manifest.json`을 Figma Desktop의 **Plugins → Development → Import plugin from manifest**에서 등록한다. 최초 가져오기와 같은 플러그인 ID를 사용해 기존의 비공개 메타데이터를 읽을 수 있게 한다. 이 설정은 한 번 수행한다.
2. 정확한 파일과 가져오기 페이지를 열고 개발 메뉴에서 **Figma Flow · 앱에 반영 0.9**를 실행한다. 이전 적용 이력이 없다면 **디자인을 편집하기 전에** ‘앱에 반영’을 눌러 원본과 일치하는 기준선을 저장한다. 첫 클릭 전에 변경했다면 원본 상태를 복구하거나 유효한 이전 적용 체인을 준비한다.
3. 0.7.0 적용을 이어받을 때는 최초 실행에 `--prior-sync PRIOR_0_7_APPLIED`를 추가한다. 값은 같은 원본·페이지·현재 프로젝트와 일치하는 직전 성공 적용의 바깥 폴더다. 임의 계획 폴더나 새 기준선으로 과거 체인을 대신하지 않는다.
4. 같은 페이지의 지원 토큰을 편집하고 **앱에 반영**을 누른다. 버튼은 페어링된 현재 페이지 하나의 네이티브 상태를 읽어 로컬 도우미로 보내고 검증 후 앱에 적용한다. 다른 페이지로 이동했다면 대상 페이지로 돌아온다. 상태의 기준선·적용·변경 없음·실패 결과를 확인한다.
5. 플러그인의 비교 화면 또는 도우미가 출력한 비교 주소를 연다. 재시작할 때는 같은 프로젝트·원본·파일·페이지·플러그인 ID와 `PRIVATE_DIR`로 도우미를 다시 실행한다. 기존 상태 체인을 보존한다.

페어링 플러그인은 loopback 주소의 인증된 쓰기 API를 사용한다. 생성된 플러그인·상태에는 비밀 페어링 키가 있으므로 앱 배포 폴더나 저장소에 넣거나 공유하지 않는다. 로컬 도우미는 Figma 계정 인증이나 원격 MCP 연결을 대신하지 않는다. 기존 비페어링 가져오기·JSON 내보내기 키트는 계속 네트워크 비활성으로 동작한다.

별도 **읽기 전용** 서버가 실제 앱을 제공하고, 네이티브 Figma 노드에서 읽은 지원 색상·치수와 브라우저의 실제 앱 스타일을 비교한다. 예상 값을 생성 CSS에서 다시 읽어 정답으로 삼지 않는다. 현재 선택자 매핑은 복습 카드 예제에 한정되며 임의 앱·레이아웃·모든 상태의 일치를 보장하지 않는다. 지원하지 않는 속성·불명확한 노드·정적 사용처 공백은 미검증으로 남긴다. 그래프에 선언된 영향 화면과 정적 코드 후보는 실제 브라우저에서 비교한 결과와 별도로 보고한다. 실제 포인터·키보드 동작 검증은 아래 절차를 따른다. 자동 테스트 성공을 실제 Figma 버튼 실행이나 런타임 비교 성공으로 기록하지 않는다.

## 치수와 실제 앱의 전후 비교: 0.9.0

0.8.0의 설정·기준선·로컬 버튼 흐름을 그대로 사용한다. 비교 범위는 기존 네이티브 색상에 다음 세 치수군을 더한다. 네이티브 측정값과 실제 브라우저의 computed style을 **CSS px**로 대조한다.

| 치수군 | 비교하는 네이티브 값과 앱 값 |
| --- | --- |
| 패딩 | 위·오른쪽·아래·왼쪽 네 방향 각각 |
| 모서리 반경 | 왼쪽 위·오른쪽 위·오른쪽 아래·왼쪽 아래 네 모서리 각각 |
| 버튼 라벨 글자 크기 | 변수 바인딩이 있는 버튼 라벨의 `fontSize`와 실제 라벨의 `font-size` |

도우미가 실행 중인 **라이브 ‘앱에 반영’ 클릭**에서 페어링된 이전 상태를 사용할 수 있을 때 실제 앱의 적용 전·후 스타일을 각각 수집해 해당 네이티브 값과 비교한다. 적용 후 CSS를 역산해 과거 실측으로 기록하지 않는다. 첫 기준선·수동 JSON 실행·이미 끝난 과거 적용 등 역사적 앱 측정이 없는 경우 전 값은 `unknown`이다. 네이티브 값 누락·혼합 값, 라벨 또는 바인딩의 부재·모호함과 지원하지 않는 매핑도 해당 항목을 `unknown`으로 남긴다. 알려진 한 항목의 일치로 미측정 항목을 통과 처리하지 않는다.

현재 실제 앱 선택자 매핑은 복습 카드 예제다. 정적 테스트·생성 CSS·그래프 선언은 실제 전후 DOM 측정의 대체물이 아니다. 비교 화면의 관측값·일치 여부·미검증 항목을 확인하고 실제 포인터/키보드 검증은 별도로 남긴다. 테스트만 통과한 경우 실제 Figma 클릭과 브라우저 전후 비교는 미검증으로 보고한다.

동일한 파일 키·페이지 ID·최초 원본 스탬프와 보호된 적용 체인을 유지한다. 토큰의 추가·삭제·별칭 연결 구조 또는 변수 바인딩을 바꿔야 한다면 기존 체인의 메타데이터를 고치지 말고 변경한 번들을 새로 가져와 새 페이지·기준선으로 시작한다. 기존 적용·재읽기 기록을 보존한다.

## 빠른 시작

다음은 보존된 수동 JSON 방식이다. 버튼 방식과 동일한 원본·스칼라 변경·생성 자산 보호 계약을 따른다.

플러그인 루트에서 실행한다. `PROJECT`는 실제 앱 프로젝트, `ORIGIN_RESOLVED`는 해당 Figma 페이지를 **처음 가져올 때 사용한** 번들의 `preview/resolved.json`, `PAGE_ID`는 재읽기에 기록된 실제 가져오기 페이지의 네이티브 ID다. 프로젝트의 `design.json`과 원본 제품 그래프를 먼저 확인한다. 번들 생성·가져오기는 [로컬 디자인 절차](local-design-audit.md)를 따른다.

1. 실제 Figma 파일에서 가져온 페이지와 변수 컬렉션을 확인하고 변경 전 재읽기를 `BEFORE_JSON`으로 내보낸다. 원본 번들과 원본 `resolved.json`을 보존한다.
2. 같은 페이지의 기존 직접 토큰 값을 편집한 뒤 변경 후 재읽기를 `AFTER_JSON`으로 내보낸다. 페이지·컬렉션·변수 ID를 유지한다. 화면 배치나 문구 변경은 이 적용 범위에 포함되지 않는다.
3. 아직 존재하지 않는 출력 폴더로 계획을 만든다.

```sh
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before BEFORE_JSON --after AFTER_JSON --page-id PAGE_ID --out NEW_DIR
```

4. `NEW_DIR/impact.html`, `result.json`, `code-scope.json`과 `token-plan/impact.json`을 읽는다. 토큰 전후 값, 별칭 전파, 선언 화면과 코드 사용처, 적용 대상·정적 분석 공백을 검토한다. 이 실행은 프로젝트를 쓰지 않는다.
5. 검토한 입력을 그대로 사용하고 **다른 새 출력 폴더**로 적용한다.

```sh
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before BEFORE_JSON --after AFTER_JSON --page-id PAGE_ID --out NEW_APPLIED_DIR --apply
```

6. 결과와 실제 파일 차이를 확인한 뒤 아래의 실제 앱 검증을 수행한다. 적용은 `design.json`과 영향받는 기존 생성 자산만 쓴다. 변하지 않은 생성 CSS는 쓰지 않으며 적용 후 해시를 기록한다. 앱 JavaScript의 동작, 원본 제품 그래프·기획서·테스트·승인 이력을 자동 수정하거나 새 기준선으로 승인하지 않는다.

전체 명령 형식은 다음과 같다. 대괄호는 선택 인자를 뜻하며 실제 명령에 넣지 않는다.

```text
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before BEFORE_JSON --after AFTER_JSON --page-id PAGE_ID --out NEW_DIR [--prior-sync PREVIOUS_RUN] [--apply]
```

## 같은 Figma 페이지에서 다음 변경 이어가기

첫 적용으로 로컬 디자인 값이 바뀌어도 Figma 페이지의 `source_sha256`은 최초 가져오기 원본의 스탬프다. 다음 변경에서 새 `resolved.json`으로 바꾸거나 Figma 메타데이터를 고쳐 일치시키지 않는다. **처음 가져온 `ORIGIN_RESOLVED`를 계속 사용**하고, `--prior-sync`로 현재 로컬 상태와 직전 적용 결과의 연속성을 확인한다.

직전 변경 후 재읽기를 다음 `BEFORE_JSON`으로, 추가 편집 후 재읽기를 다음 `AFTER_JSON`으로 지정한다. `PREVIOUS_RUN`은 직전 **성공한 `--apply` 실행의 바깥 폴더**이며 `token-plan/`이나 계획만 만든 폴더가 아니다.

```sh
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before NEXT_BEFORE_JSON --after NEXT_AFTER_JSON --page-id PAGE_ID --out NEXT_PLAN_DIR --prior-sync PREVIOUS_RUN
python3 tools/apply_figma_change.py --project PROJECT --resolved ORIGIN_RESOLVED --before NEXT_BEFORE_JSON --after NEXT_AFTER_JSON --page-id PAGE_ID --out NEXT_APPLIED_DIR --prior-sync PREVIOUS_RUN --apply
```

현재 프로젝트가 직전 적용의 기록된 상태와 다르거나 입력·페이지·원본 체인이 일치하지 않으면 먼저 그 차이를 검토한다. 계획만 만든 결과를 성공한 적용 이력으로 대신하지 않는다. 새 Figma 가져오기로 페이지와 컬렉션을 바꾸었다면 새 가져오기 기준선을 준비한다.

## 출력과 영향 범위 읽기

| 출력 | 읽을 내용 |
| --- | --- |
| `result.json` | 계획/적용 결과, 입력 고정과 쓰기 결과·해시 |
| `impact.html` | 오프라인 변경 영향 검토 화면 |
| `code-scope.json` | 실제 프로젝트 소스에서 정적으로 찾은 클래스 사용 후보와 분석 공백 |
| `token-plan/impact.json` | 직접 변경 토큰, 상속 별칭, 컴포넌트 변형, 그래프에 선언된 화면과 의존 경로 |
| `token-plan/dependencies.json` | 원본 디자인과 제품 그래프에서 만든 영향 투영 |
| `token-plan/design.json`, `resolved.json` | 제안 디자인과 해석된 값. 두 파일 모두 `token-plan/` 안에 있다 |
| `token-plan/assets/tokens.css`, `components.css` | 제안 생성 CSS |
| `token-plan/report.md` | 토큰 계획의 읽기용 설명과 제한 |

그래프의 `declared_screen_ids`는 디자인 선언을 따라 도달한 화면이다. 실제 앱에서 해당 화면이 그 변형을 렌더링한다는 증거는 아니다. 앱의 정적 클래스 사용처는 `Button--primary` 같은 생성 클래스가 소스에 등장하는 별도 관찰이다. 소스에 클래스가 있어도 실행 경로·상태에 따라 DOM에 없을 수 있다. 동적 클래스 조합, 런타임 렌더링, 다른 스타일의 덮어쓰기나 정적 분석이 다루지 못한 구문은 공백으로 남기고 실제 앱을 확인한다. 정적 공백을 사용처 없음이나 전체 영향 없음으로 바꾸지 않는다.

기존 생성 CSS가 현재 디자인에서 생성될 내용과 다르면 **덮어쓰기를 중단하고 실패**한다. 수동 CSS 변경을 강제로 없애거나 새 기대값으로 간주하지 않는다. 해당 차이의 의도를 확인하고 로컬 디자인·생성 자산의 기준을 정리한 뒤 새 출력 폴더에서 다시 계획한다.

## 허용되는 토큰 변경과 보존 범위

하나의 고정 컬렉션·기본 모드에서 기존 직접 스칼라 토큰만 바꾼다. 타입은 `color`, `dimension`, `number`, `fontFamily`다. 색상은 8비트 sRGB hex로 왕복 가능해야 하며 Figma의 정확한 float32 저장 표현도 허용한다. 차원은 원본 `px`/`rem` 단위를 보존하고 `1rem = 16px`로 변환한다. 구조화된 원본 값은 보존하되 여기서 편집하지 않는다.

별칭 값은 직접 쓰지 않고 원본 참조를 따라 전파한다. 별칭 연결, 토큰 이름·타입·네이티브 ID, 컬렉션 소유권·모드 변경은 적용 대상이 아니다. 선택한 페이지의 레이아웃·텍스트·바인딩 변경과 선택 컬렉션 밖의 차이는 보고만 한다. 다른 가져오기 페이지와 공유한 컬렉션이나 모호한 토큰 식별자는 적용 전에 해결한다.

## 실제 Figma와 앱 검증

실제 Figma 증거에는 파일·페이지 식별자, 관찰 시각, 편집한 변수와 전후 내보내기 경로를 남긴다. 시뮬레이션 Plugin API 검사나 제공 JSON의 통과를 실제 Figma 가져오기 성공으로 보고하지 않는다. Figma를 열지 못했다면 출처·실제 파일 상태는 미검증으로 남긴다.

앱 적용 후 승인된 실제 브라우저에서 영향 화면을 연다. 실제 DOM의 변형 클래스와 computed style을 확인하고 기본·hover·focus·disabled 등 해당 상태를 각각 살핀다. hover나 상태별 CSS가 기본 토큰 값을 덮어쓰면 그 실제 결과를 따로 기록한다. 색이 바뀐 버튼은 포인터로 실제 클릭해 의도한 동작을 확인하고, 해당 키보드·좁은 화면 상태와 콘솔 오류도 확인한다. DOM을 조작하거나 함수를 직접 호출한 결과로 실제 포인터 상호작용을 대신하지 않는다.

완료 보고에는 로컬 입력/토큰 계획, 프로젝트 적용, 정적 클래스 범위, 실제 Figma 관찰, 실제 브라우저·포인터 동작을 분리한다. 관련 프로젝트 테스트와 [검토 후 재개](graph-contract.md#local-freshness-manifests)가 필요하면 그 절차를 별도로 수행한다. 도구 성공만으로 앱 전체, 전체 영향 범위나 새 인수 기준선이 검증되었다고 주장하지 않는다.

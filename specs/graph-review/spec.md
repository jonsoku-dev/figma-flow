# 한 그래프에서 직군별 검토 자료 만들기

[정본 그래프](graph.json)는 세 직군의 요구사항·인수 기준·검증 경로를 연결한다. 이 문서는 graph를 새로 작성하거나 기존 관계를 바꾸는 절차가 필요한 경우에 사용한다.

## 사용

1. 제품 graph에 안정적인 `id`, `title`, `version: 1`, 기존 형식의 nodes/edges를 기록한다. 예전 graph에 이미 `design_system.id`가 있으면 그 ID를 쓴다. 파일 위치나 수정 시각에서 소유권을 유추하지 않는다.
2. 전달할 노드를 ID로 고른다. 최대 24개 노드, 그 노드끼리의 관계 최대 48개까지 한 검토 화면에서 읽을 수 있다. 큰 graph는 더 작은 범위로 나눠 선택한다. 항목의 원래 타입·상태·관계 방향과 source graph SHA를 유지한다.
3. Design에서는 `tools/native_edit.py graph-review`로 plan을 만들고 기존 workspace의 `native-edit` 작업으로 준비한다. FigJam과 Slides는 같은 graph와 선택을 `tools/figma_sdk_project.py init --review-graph`에 전달한다. FigJam은 요구사항·행동 추적표와 연결선을 만들고 Slides는 관계 및 근거를 설명하는 검토 덱을 만든다.
4. 작업 후 실제 node와 반환된 증거를 비교한다. 알 수 없는 값과 권한·편집기 조건은 각각 기록한다. 사용자가 수정한 산출물과 오래된 계획의 충돌은 별도 검토 대상으로 남긴다.

```sh
python3 tools/native_edit.py graph-review --graph specs/graph-review/graph.json --node REQ-plan --node SCR-plan --node AC-plan --node TEST-plan --file-key FILE_KEY --page-id PAGE_ID --out NEW_PLAN_JSON
python3 tools/figma_sdk_project.py init NEW_FIGJAM_DIR --editor figjam --recipe figjam-review-planner --review-graph specs/graph-review/graph.json --node REQ-plan --node SCR-plan --node AC-plan --node TEST-plan
python3 tools/figma_sdk_project.py init NEW_SLIDES_DIR --editor slides --recipe slides-flow-review --review-graph specs/graph-review/graph.json --node REQ-plan --node SCR-plan --node AC-plan --node TEST-plan
```

플러그인 프로젝트의 실제 ID 등록과 빌드는 [SDK 안내](../../docs/figma-sdk-project.md)를 따른다. [FigJam](../../docs/figjam-review-planner.md)과 [Slides](../../docs/slides-flow-review.md)의 익숙한 에디터에서 동일 그래프를 검토할 수 있다.

## 실제 인수 범위

Magic UI 템플릿 네 개를 각각 프로덕션 빌드하고 검토 대상으로 사용했다. 원본 ZIP과 앱 소스·스크린샷은 공유 배포에서 제외했다. 테스트 그래프에는 각 앱의 시나리오, 화면, 조작한 요소, SSR 입력 해시, 실제 브라우저 관측을 연결했다.

| 사용 흐름 | 실제 관측 |
| --- | --- |
| Portfolio | 경력 항목 클릭 시 접힘 → 펼침 → 접힘. 프로필 이미지 원본 너비 600px. |
| Codeforge | 월별 12·24·0 달러가 연간 120·240·0 달러로 전환. 원래 월별 가격으로 복귀. |
| DevTool | 글 목록에서 상세 문서로 이동. 제목과 본문 헤딩, 실제 폰트 리소스 2개 확인. |
| SaaS | 로그인에서 가입으로 이동. 이메일 입력 타입과 필수 속성, 회원가입 필드 확인. |

실제 Design 페이지의 네이티브 검토 보드, 개인 FigJam 초안, 개인 Slides 초안이 같은 20개 노드와 16개 관계에서 생성됐다. FigJam은 스티키 21개·표 1개·셀 84개·코드 블록 1개·커넥터 16개를 반환했다. Slides는 7행·21슬라이드·텍스트 42개를 반환했다. 같은 입력의 재실행 후 수량을 대조했다. 각 앱을 재현한 편집 가능한 **화면 전체** 변환, 결제·로그인 서버의 기능 검증은 이 그래프 보드의 인수 범위에 포함되지 않는다.

정본은 기존 JSON graph다. 선택된 ID를 해시 맵에 넣고 해당 ID 사이의 관계만 순회한다. 네이티브·SDK 결과에는 그래프와 선택의 식별자를 남기고 모델마다 별도 DB나 복제된 요구사항 목록을 두지 않는다.

로컬 Mac에서 디스크의 작은손 graph(816,936바이트)를 읽고 구조 검증 후 REQ-006·AC-006·TEST-006을 투영한 20회의 중간값은 11.61ms였다. 네 템플릿 검토 graph의 전체 투영은 0.37ms였다. 이 수치는 로컬 Python 투영만 측정하며 Figma 렌더링과 네트워크는 포함하지 않는다. 현재 범위에서 SQL 캐시를 도입할 이득은 관측되지 않아 JSON 정본과 메모리 인덱스를 사용한다.

## 실제 API 근거를 다시 집계하기

`python3 tools/review_api_coverage.py`는 이전 릴리스의 감사 대상과 [현재 관측 그래프](api-observations.json)를 정확한 멤버 ID로 결합한다. 같은 멤버가 여러 종류의 노드나 여러 차례의 읽기에서 관측돼도 하나로 집계한다. 계산에는 원시 파일 키·실제 Figma 노드 ID·원본 ZIP이 필요하지 않다.

이번 Design 파일에서는 GRID 프레임, 타원, 불리언, 섹션, 메인 컴포넌트, 인스턴스를 선택했다. 0.28 기준의 미확인 속성 중 이 선택에서 조사할 수 있는 90개 **노드–속성 조합**을 70개와 20개로 나눠 실제 게터로 읽었다. 90개 모두 성공했고 고유 공개 멤버는 27개였다. 같은 70개를 다시 읽었을 때 상태 일치 70개였다. 텍스트·사각형·컴포넌트 세트를 추가한 최종 조사에서는 9개 노드의 141개 조합(111+30)을 읽어 모두 성공했고, 누적 그래프에는 고유 멤버 37개를 기록했다. FigJam과 Slides의 제작 API 12개를 더하면 새로 관측한 멤버는 총 49개다. 이전 78개와 합친 127/1,382(9.19%)는 실제 관측의 하한이다. 나머지 1,255개에는 편집기 및 권한별 API, 타입 속성과 미관측 구현이 포함된다. 제품 전체 지원률로 해석하지 않는다.

현재 Slides 경로는 `getCanvasGrid` 및 `setCanvasGrid`를 사용한다. 0.28의 역사적 미구현 목록에 있는 deprecated `getSlideGrid` 및 `setSlideGrid`를 새 코드에 재도입하지 않았다.

HTML 입력의 새 오프라인 매핑은 브라우저가 받은 리소스 URL(쿼리 포함), 응답 바이트와 원본 파일을 명시적으로 연결한다. 각 템플릿에서 Portfolio 22개, Codeforge 12개, DevTool 5개, SaaS 6개의 같은 출처 HTTP 대상을 입력 최신성 검사에 반영했다. 같은 원본 파일에서 서로 다른 최적화 URL이 만들어질 수 있어 고유 로컬 파일의 수는 각각 22·12·4·3개였다. [검증한 입력 형식](../../docs/html-asset-map.md)과 [읽기 전용 API 조사 명령](../../docs/native-api-probe.md)을 참고한다.

동일 원본에서 작은 부분 그래프를 선택한 경우를 별도로 검증했다. 두 선택은 source SHA를 공유하고 선택 SHA가 다르다. 5노드·4관계의 FigJam 보드와 6장짜리 Slides 덱은 기존 전체 선택과 함께 존재했다. FigJam의 초창기 source-SHA-only 보드는 메타데이터·텍스트·연결이 정확히 일치하는 대상을 찾아 123개 노드 그대로 이관했고, 이어진 같은 입력 실행도 노드를 추가하지 않았다.

Slides의 가장 오래된 시험 덱은 전체 슬라이드 ID를 첫 행 한 곳에만 기록했고, Figma가 grid 적용 후 장표 이름을 숫자로 표시했다. 처음에는 같은 graph의 덱이 한 벌 더 생성되는 문제를 재현했다. 실제 grid의 순서·각 행의 전체 자식·개별 슬라이드 ID·원문 텍스트·관계를 함께 확인하도록 수정했다. 새 초안에서 가장 오래된 형태로 만든 7행·21슬라이드·텍스트 42개(전체 71개 노드)를 같은 ID로 이관하고 재실행했다. 불일치 자료는 원본을 보존한 채 충돌로 남긴다.

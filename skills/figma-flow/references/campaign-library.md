# 캠페인 근거 라이브러리

`library/campaigns.json`의 한국·일본 공개 자료를 카테고리별로 조회하고 재사용 가능한 검증 계획과 오프라인 HTML 카탈로그를 만든다. 실행 위치는 플러그인 루트다. Python 표준 라이브러리만 사용하며 외부 요청은 하지 않는다.

```sh
python3 tools/campaign_library.py list
python3 tools/campaign_library.py list --market KR --category prelaunch
python3 tools/campaign_library.py plan --category participation --market JP
python3 tools/campaign_library.py report --out /tmp/campaign-catalog-new.html
python3 tools/campaign_library.py --data /path/to/library.json list
```

카테고리 ID는 `list`의 `categories`에서 선택한다. `--data`는 하위 명령 뒤에도 사용할 수 있다.

- `list [--market KR|JP] [--category ID]`: `version`, `captured_on`, `categories`, `sources`, `patterns` JSON을 출력한다. 출처를 시장·카테고리로 먼저 고르고, 남은 출처를 참조하는 관련 패턴만 반환한다. 각 패턴의 `source_ids`도 선택된 출처로 제한한다.
- `plan --category ID [--market KR|JP]`: 패턴별 `pattern_id`, 관측, 적용 제안, 한계, `evidence`의 출처 ID·HTTPS URL·관측 근거·관측일, 구체적인 `checks`를 JSON으로 반환한다. 계획과 각 검사는 `status: "untested"`, `verification: "manual"`이다. 매칭 자료가 없으면 패턴 배열이 비어 있는 미검증 계획을 반환한다.
- `report --out NEW.html`: 카테고리·시장·텍스트 필터, 출처 원문 링크, 도출 패턴, 선택한 카테고리·시장의 계획 JSON과 다운로드를 제공하는 독립 HTML 파일을 생성한다. 검색은 카드에만 적용되며 계획은 카테고리·시장 전체를 포함한다. JavaScript 없이도 전체 출처와 패턴은 읽을 수 있다. 기존 파일·심볼릭 링크와 `.html` 이외 출력은 거부한다. 상위 출력 디렉터리는 미리 존재해야 한다.

성공 종료 코드는 `0`, 데이터·파일 오류는 `1`, CLI 사용법 오류는 `2`다. `report`는 생성한 경로와 실제 출처·패턴 수를 JSON으로 출력한다.

## 데이터 계약

최상위 객체는 `version: 1`, ISO 날짜 문자열 `captured_on`, `categories`, `sources`, `patterns` 배열을 갖는다.

- 카테고리: 고유 `id`, `name` 문자열.
- 출처: 고유 `id`, `title`, 자격 증명 없는 HTTPS `url`, `market` (`KR` 또는 `JP`), `type`, `evidence`, `observed` 문자열, 카테고리 ID 배열 `categories`. 선택 필드 `visual`은 `surface` 문자열과 비어 있지 않은 `observations` 문자열 배열을 갖는 객체 배열이다. 출처 카드의 “시각 관측 기록”을 열면 관측 환경과 항목을 읽을 수 있다.
- 패턴: 고유 `id`, `title`, 카테고리 ID `category`, 출처 ID 배열 `source_ids`, `observation`, `application`, `limits` 문자열, 비어 있지 않은 검사 문자열 배열 `checks`.

ID에는 영문자·숫자·밑줄·하이픈을 사용하고 첫 글자는 영문자 또는 숫자다. 필수 텍스트와 참조 배열은 비어 있을 수 없다. 잘못된 ID·중복·참조·URL은 렌더링 전에 거부한다. HTML 및 내장 JSON은 데이터가 실행되지 않도록 이스케이프한다.

## 근거와 검증의 경계

출처 관측은 해당 자료를 읽은 근거이며 제품 성과·작동·접근성의 통과 증거가 아니다. 패턴은 적용 가설이다. 검증 계획을 대상 화면과 기능에 맞춰 실행하고, 실제 결과·환경·화면 또는 로그 근거를 별도로 남긴다. CLI와 카탈로그는 자료를 자동 갱신하거나 검사를 실행하거나 통과 상태를 부여하지 않는다. 원문 링크를 열면 네트워크 연결이 필요하다.

다른 카테고리에 태그된 출처를 참조하는 경우 전체 조회의 `cross_category_analogy_source_ids`와 카탈로그의 “타 카테고리 유추” 표기로 구분한다. 카테고리별 계획에는 해당 카테고리로 태그된 출처만 `relationship: "same_category_observation"`과 `source_categories`를 붙여 포함한다. 동일 카테고리의 관측 출처가 없는 패턴은 해당 계획에 포함하지 않는다. 이는 그 카테고리에서 실제로 관측했다는 오해를 피하기 위한 제한이다.

계획의 `observation`은 시장·카테고리 필터로 다시 쓴 문장이 아니라 원본 패턴 전체의 종합이다. 계획과 각 패턴의 `synthesis_scope`가 이를 명시한다. 패턴의 범위 객체에는 원본 카테고리, 전체 시장, 전체 `source_ids`, `filtered: false`가 있다. `supporting_sources`는 원문 종합의 모든 출처 ID·URL·시장·카테고리·관측 근거를 보존하며 `relationship`으로 동일 카테고리 관측과 `cross_category_analogy`를 구분한다. 반면 `evidence`는 선택한 카테고리·시장에 해당하는 근거만 포함한다. 예를 들어 KR 계획의 관측 문장에 일본 사례가 남아 있으면 그 출처는 전체 `supporting_sources`에서 확인하고, KR의 검증 근거로 해석하지 않는다.

```sh
python3 -m unittest discover -s tests -p 'test_campaign_library.py'
```

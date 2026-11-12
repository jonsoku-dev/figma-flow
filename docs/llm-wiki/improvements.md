# 실패 기반 개선 제안

`tools/patch_knowledge_check.py`는 Git으로 고정한 개선 전·후 코드를 임시 아카이브에 풀고 같은 재현 명령을 다시 실행한다. 저장된 실행 결과를 입력으로 받지 않는다. 실행할 제안과 테스트 코드는 호출자가 검토한다. `--execute`는 그 명령 실행을 명시하며, 보안 격리나 외부 행동의 추가 권한을 제공하지 않는다.

## 제안을 작성하기

제안은 `figma-flow-improvement-v1` JSON이다. `base`와 `target`은 실제 전체 커밋으로 채운다. `base`는 `target`의 엄격한 조상이며 `target`은 현재 HEAD여야 한다. 실행하는 검사 스크립트·명명한 unittest 모듈·Node 검사 파일은 양쪽 커밋의 Git blob과 파일 모드가 같아야 한다. 재현을 새로 작성하거나 검사 기준을 바꾸려면 커밋 쓰기 권한 소유자가 수정 전 동작을 검사하는 새 기준 커밋에 먼저 보존한다. 그 뒤 제품 구현만 바꾼 별도 target을 검사한다. 실패 assertion을 지우거나 print로 바꾼 diff는 개선으로 통과하지 않는다.

```json
{
  "schema": "figma-flow-improvement-v1",
  "base": "수정 전 전체 커밋",
  "target": "현재 HEAD의 전체 커밋",
  "problem": "직접 연결된 사진이 바뀌어도 이전 입력 근거가 계속 사용된다.",
  "result": "사진의 실제 바이트가 바뀌면 입력 근거가 달라진다.",
  "rationale": "HTML 본문 외에 소비한 파일의 바이트도 입력에 포함해야 한다.",
  "compatibility": "과거 입력 결과는 현재 도구로 다시 준비하고 원본 파일을 보존한다.",
  "limits": "이 재현은 직접 연결된 로컬 사진만 다루며 재귀 CSS는 별도다.",
  "follow_up": "재귀 CSS의 실제 누락 사례를 별도로 재현한 뒤 확장한다.",
  "related": ["docs/llm-wiki/README.md"],
  "scope": ["src/input.py"],
  "criteria": ["ASSET-CHANGED"],
  "reproduction": {
    "criterion": "ASSET-CHANGED",
    "argv": ["python3", "tests/reproduce_asset.py"],
    "failure_contains": "changed asset must invalidate evidence"
  },
  "checks": [
    {"criterion": "ASSET-CHANGED", "argv": ["python3", "tests/reproduce_asset.py"]}
  ]
}
```

이 예시는 스키마 설명이다. 존재하지 않는 경로나 설명용 커밋 문자열로 실행하면 거절된다. `scope`는 base와 target 사이에 실제로 바뀐 모든 경로의 정렬된 고유 목록이다. 예시의 검사 파일은 기준 커밋부터 존재하고 구현 diff에서는 그대로 유지한다. 조건 ID마다 검사 하나를 연결하며 재현 명령도 한 번 포함한다. 미기재 조건·중복·임의의 `passed`/`completed` 필드는 거절된다. 의미 설명 6개와 관련 Wiki 경로도 필수다.

## 실행과 결과 해석

```sh
python3 tools/patch_knowledge_check.py gate .figma-flow/improvement.json --execute --output .figma-flow/improvement-result.json
```

실행은 개선 전 예상 assertion 실패, 개선 후 모든 검사 성공, 현재 커밋·소스 신선도 순으로 확인한다. 예상 문구가 일반 출력에 등장한 것만으로는 실패 재현을 인정하지 않는다. 지원하는 재현은 stderr의 마지막 Python traceback에 있는 최종 `AssertionError` 메시지 또는 직접 실행한 Node의 `AssertionError [ERR_ASSERTION]` 메시지다. Node test runner의 TAP 같은 다른 형식은 재현을 직접 스크립트로 좁히거나 지원 코드를 검증하고 확장한 뒤 사용한다. 시간 초과는 실패다. 기본 명령 제한은 60초이며 `--timeout`으로 1~300초를 지정할 수 있다.

명령은 PATH의 `python`·`python3`·`node`와 양쪽 커밋에 존재하는 상대 경로 스크립트만 사용한다. Python `-B -m unittest`의 추적된 dotted module과 Node `--test`의 추적된 파일도 지원한다. shell 표현식·절대 경로·홈 경로·동적 `-c`/`-e` 코드를 넣지 않는다. 임시 아카이브는 링크·특수 파일·gitlink를 거절한다. 환경 변수를 최소화하지만 검토한 코드는 여전히 호스트에서 실행된다.

결과에는 실제 명령·종료 코드·출력 해시·고정 커밋을 남긴다. 출력 원문은 사용자 정보를 포함할 수 있으므로 `.figma-flow/`의 로컬 결과로 보존한다. 공유 Wiki에는 필요한 사실·검사 범위·종료 코드·한계를 추려 적는다. 출력의 `status`를 편집해도 다음 실행의 판정에 쓰이지 않는다.

현재 소스에 미커밋 변경이 있으면 개선 검사를 완료로 인정하지 않는다. Wiki·CHANGELOG의 기록 갱신은 예외로 허용한다. 별도의 커밋 검사가 필요하다면 해당 소스를 먼저 고정하고 새 target으로 다시 실행한다. 실제 Figma·브라우저·실기기 검증은 이 코드 검사와 별도로 보고한다.

검증기 자체의 결함을 고칠 때도 별도의 안정된 독립 검사를 선택한다. 고정한 검사 파일이 충분한 조건을 검사하는지와 읽는 헬퍼·입력 전체가 타당한지는 독립 검수로 확인한다. blob 동일성은 선택한 기준의 변경을 막으며 모든 의미적 우회나 운영체제 격리를 증명하지 않는다.

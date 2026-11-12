# 제품 변경과 패치 기록을 함께 발행하기

기록 작성자는 현재 사용자의 요청과 저장소 소유권에서 범위를 정한다. 버전·Git index·커밋·push·태그·설치 권한은 Wiki에서 얻지 않는다. 한 파일에는 한 작성자만 둔다. 원시 Figma 자료·control/pairing 값·개인 설치 경로는 공유 기록에 복사하지 않는다.

## 제품 커밋과 기록 발행을 구분한다

자신의 전체 Git SHA를 같은 커밋에 포함할 수 없으므로 제품 변경과 후속 기록 발행을 나눈다.

1. 실제 실패를 재현하고 검사 파일을 기준 커밋에 고정한다. 새 인수 기준이 필요하면 구현 전에 따로 보존한다. 수정 전 예상 assertion 실패와 수정 후 동작을 같은 검사로 비교한다.
2. 허용한 제품 변경·테스트·버전·정책·CI를 로컬 제품 커밋으로 고정한다. 실패 기준 커밋만 원격의 최종 상태로 발행하지 않는다.
3. 개선 제안을 실제 base/target·정확한 변경 범위로 작성하고 검토한 명령을 실행한다. target은 실행 시점의 HEAD여야 하며 검사 파일의 blob·모드는 양쪽에서 같아야 한다.

```sh
python3 tools/patch_knowledge_check.py gate .figma-flow/improvement.json --execute --output .figma-flow/improvement-result.json
python3 tools/patch_knowledge.py sync --ref HEAD
```

4. 새 `patches/<전체-SHA>.md`의8개 필수 항목을 실제 diff로 채운다. 과거 문서 발행·검사 기준 커밋도 새 목록에 포함되면 각각 기록한다. CHANGELOG에는 사용자 변화만 짧게 적고 상세 기록과 연결한다. 같은 버전 문자열의 후속 커밋과 실제 릴리스 태그 범위는 구별한다.
5. 기존 수동 본문이 보존됐는지 대조하고 생성 메타데이터를 다시 동기화한다. 문서의 의미와 실제 변경이 맞는지 독립 검수를 받는다.

```sh
python3 tools/patch_knowledge.py sync --ref HEAD
python3 tools/patch_knowledge.py verify --ref HEAD
python3 tools/patch_knowledge_legacy.py verify --wiki docs/llm-wiki/legacy
python3 -B -m unittest discover -s tests -p 'test_patch_knowledge*.py'
```

6. `docs/llm-wiki/**`와 `CHANGELOG.md`만 후속 발행 커밋에 담는다. 제품 코드·테스트·스킬·AGENTS·CI가 추가되면 새 제품 소스로 돌아가 기록과 검증을 갱신한다.
7. 발행 뒤 기본 verify를 다시 실행해 후속 커밋이 문서 발행으로만 분류됐는지 확인한다. 현재 사용자가 허용한 원격 발행·릴리스·설치는 검증한 최종 소스로 수행한다.
8. 브라우저·Figma·설치본·외부 서비스의 실행 범위와 미검증 조건은 실제 관찰로 따로 기록한다. Wiki 검사나 CI 성공을 제품 인수로 대신하지 않는다.

최초 구축의 예는 [e3bb050 제품 통합](patches/e3bb0505b011f77a656e096b821c7d0d01f2990c.md)과 [25b17f9 기록 발행](patches/25b17f9cc0cd13f73f4545403fbef0f9d6ba1a6c.md)이다. 이는 해당 소스 시점의 기록이며 이후 설치 상태나 모든 회귀 케이스의 통과를 뜻하지 않는다.

## 보존 계보를 다시 검사한다

일반 fork CI는 [보존 계보](legacy/README.md)의 구조·해시를 검사한다. 원본 객체를 가진 운영자는 임시 bare Git과 `legacy verify --source-git`으로 원문을 다시 대조한다. 원본이 없는 검사를 source-backed로 표시하지 않는다. 자신의 fork에서 재실행한 결과와 원래 저장소의 과거 결과를 구분한다.

# 통합과 다음 기록 갱신

## 소유권

버전·Git index·커밋·push·tag·릴리스·설치 갱신은 부모 작업 소유다. 이 작업은 그런 변경을 수행하지 않았다. 통합 가능한 파일의 정확한 목록과 동결 상태는 로컬 `.figma-flow/coordination/patch-wiki/status.json`에 있다. 이 로컬 상태나 보고 문구를 성공 근거로 재사용하지 않고 실제 검사를 다시 실행한다.

## 첫 제품 커밋 뒤

도구·스킬·정책·검사 파일이 처음 커밋되면 새 전체 커밋 ID로 카탈로그와 새 상세 기록을 갱신해야 한다. 자신의 커밋 해시를 같은 커밋에 포함할 수 없기 때문에 후속 Wiki/CHANGELOG 발행을 구분한다. 현재 카탈로그는0bd8177까지의 역사이며 아직 커밋되지 않은 이 기록 도구 자체를 이미 기록한 것으로 주장하지 않는다.

통합 소유자가 제품 커밋을 만든 후, 기록 파일의 쓰기 소유권을 한 작업자에게 넘기고 다음 순서로 실행한다.

```sh
python3 tools/patch_knowledge.py sync --ref HEAD
```

새 `docs/llm-wiki/patches/<새-전체-커밋>.md`의8개 항목을 실제 diff로 작성한다. 기록 시스템을 릴리스에 포함했다면 그 사용자 변화도 CHANGELOG와 해당 버전 기록에 반영한다. 기존 본문은 보존하고 새 커밋을 임의 버전으로 소급 합치지 않는다.

```sh
python3 tools/patch_knowledge.py sync --ref HEAD
python3 tools/patch_knowledge.py verify --ref HEAD
python3 tools/patch_knowledge_legacy.py verify --wiki docs/llm-wiki/legacy
python3 -B -m unittest discover -s tests -p 'test_patch_knowledge*.py'
```

이후 `docs/llm-wiki/**`와 `CHANGELOG.md`만 담는 발행 커밋을 만든다. 발행 후에는 다시 기본 verify를 실행해 Git이 후속 커밋을 문서 발행으로만 분류했는지 확인한다. 제품 코드·테스트·스킬·AGENTS·CI를 그 후속 커밋에 섞으면 이전 카탈로그로 통과하지 않는다. 릴리스 태그는 별도 사용자 권한 아래 통합 소유자가 확정한다.

## 0.26.1 후보

현재 CHANGELOG 후보는0bd8177의 런타임 수정과 부모의 검증표 정리를 설명한다.61개 케이스는 모두 unverified이며183개 부분 근거가 연결됐다는 범위만 기록한다. 이 지식 시스템의 코드까지 같은 릴리스에 넣을지는 통합 소유자가 최종 범위를 정하고 그 사실을 추가한다. 실제 새 태그·설치 성공을 이 문서로 대신하지 않는다.

## 역사 자료 재검사

일반 fork CI는 보존 계보의 구조·해시를 검사한다. 원본 bundle을 가진 운영자는 임시 bare Git에서 source-backed 검사를 다시 할 수 있다. [보존 계보](legacy/README.md)의 출처 해시와 실제 객체를 대조하며, 개인 보관 경로나 원시 사용자 데이터를 배포 문서에 복사하지 않는다.

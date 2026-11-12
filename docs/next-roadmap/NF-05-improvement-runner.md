# NF-05 포크 패치·근거 교환과 개선 러너

상태는 **PROPOSED**다. 현재 patch knowledge와 독립 재현 검사를 재사용하는 명시적 로컬 CLI 기능이다.

## 기능 계약

사용자는 포크·다른 checkout에서 만든 수정과 그 근거를 원본에 가져와 검토하고, 검사가 중단되어도 무엇을 실행했는지 잃지 않고 재개하고 싶다. 결과는 안전하게 검사할 교환 패키지와 결정적 단계 러너다. 러너는 등록된 작은 작업을 한 번씩 진행하고 상태를 원자적으로 남긴다.

hook, Goal, CUA, 상시 LLM 세션에 의존하지 않는다. 자동 수정 생성·자동 승인·자동 merge/push·원격 다운로드·host wakeup은 제외한다. CLI가 종료되거나 호스트가 멈추면 사용자 또는 외부 호출자가 다시 실행해야 한다. LLM의 100% 지속 실행을 보장하지 않는다.

## 현재 경로와 확장 위치

`tools/patch_knowledge.py`의 `sync`, `verify`, `inventory`, `atomic`이 Git 기록과 Wiki를 검증한다. `tools/patch_knowledge_check.py`의 `validate`, `regular_blob`, `snapshot`, `archive`, `run`은 exact base/target 커밋, 전체 scope, 고정 검사 파일, 격리 아카이브와 재현/검증을 처리한다. 기존 checker를 runner 안에 복제하거나 느슨하게 다시 만들지 않는다.

현재 checker는 target이 HEAD이고 base가 strict ancestor인 커밋을 요구한다. 포크에서 온 dirty patch는 이 검사를 바로 통과할 수 없다. `skills/patch-knowledge/SKILL.md`와 `docs/llm-wiki/integration.md`의 정본 통합 순서가 유지된다. 근거 교환 패키지는 승인이 아니며 검사를 실행할 권한도 스스로 만들지 않는다.

Git의 `apply --check`는 적용 가능성을 검사한다. `--3way`는 blob이 있을 때 병합을 시도하며 충돌을 남길 수 있다. 초기 버전은 `--check` 기반 preflight만 제공하고 자동 three-way는 제외한다. [Git 공식 apply 문서](https://git-scm.com/docs/git-apply)를 따른다.

## 교환 데이터 설계

교환 패키지는 plain JSON manifest와 명시한 상대 경로 파일로 구성한다. 초기 버전은 tar/zip import를 지원하지 않아 archive 탈출·압축 폭탄 범위를 줄인다. manifest 제안은 아래와 같다.

```json
{"schema":"figma-flow-patch-exchange-v1","id":"stable-id","baseCommit":"40hex","targetCommit":"40hex","patch":{"path":"change.patch","sha256":"sha256"},"scope":["tools/example.py"],"checker":{"commit":"40hex","path":"tools/patch_knowledge_check.py","blob":"git-blob-id","mode":"100644"},"evidence":[{"path":"evidence/result.json","sha256":"sha256","kind":"automated-test","trust":"unverified-import"}]}
```

전체 commit·patch·파일 hash를 확인하고 중복 경로, 절대 경로, `..`, symlink, Git metadata 쓰기, scope 밖 diff, binary payload 상한 초과를 거절한다. 파일당 8 MiB·전체 32 MiB를 초기 제안 상한으로 둔다. imported evidence는 원래 작성자 주장과 로컬 재검증 결과를 분리한다. screenshot이나 JSON에 실제 계정·개인 문구·native raw readback·토큰·호스트 경로가 있으면 공유 단계에서 거절한다. 단순 regex만으로 완전한 비밀 제거를 보장하지 않으며 사용자 검토 전 공개하지 않는다.

Git bundle은 초기 버전의 필수 형식이 아니다. target commit을 로컬에서 확인할 수 없으면 `needs-local-commit`을 반환한다. 원격 fetch, commit 생성, 기존 checkout의 patch 적용을 자동 실행하지 않는다. 원본에 반영하는 실제 쓰기는 별도 권한과 한 writer 범위에서 통합 담당자가 수행한다.

## 러너의 상태와 인터페이스

새 CLI 제안은 `python3 tools/improvement_runner.py inspect <exchange-dir>`, `verify <exchange-dir> --state <private-dir>`, `status --state <private-dir>`, `resume --state <private-dir>`다. 제안 명령은 아직 구현되지 않았다. `inspect`는 실행하지 않는다. `verify`는 현재 권한으로 검토한 proposal의 checker 실행만 맡는다. manifest 안 임의 argv나 shell 문자열을 실행하지 않는다. 기존 proposal의 argv는 untrusted code이므로 사전 표시·검토와 실행 환경 제한을 유지한다.

상태는 `received → inspected → ready → running → verified`다. `blocked`, `failed`, `interrupted`는 완료가 아니다. step ID·입력 digest·checker commit/blob/mode·attempt·exit code·bounded log digest를 기록한다. state 파일과 append history를 별도 writer가 건드리지 않게 POSIX lock을 둔다. state.tmp 작성·fsync·replace 후 history를 기록하며 재시작 시 step/event ID로 중복 기록을 제거한다. state와 history가 불일치하면 마지막 완료 step을 추측하지 않고 `interrupted`로 두어 재검증한다.

검사 시작 전에 HEAD·scope fingerprint와 checker identity를 고정한다. 실행 중 변경되면 결과를 폐기한다. checker 파일 또는 검사 파일의 blob/mode가 바뀌면 `checker-mismatch`다. 동일 criterion 이름/명령 문자열은 동일 기준의 증명이 아니다. 실행 완료 marker 없는 step은 재실행 가능 여부를 확인하고 read-only 검사만 재실행한다. 임의 mutation이나 결제 같은 작업은 등록할 수 없다.

## 표시·실패·개인정보·접근성

CLI는 단계·마지막 실제 exit code·다음 필요한 행동을 텍스트와 JSON으로 제공한다. 색상·spinner에만 의존하지 않는다. 로그는 제한된 크기이며 토큰·절대 경로를 공유 출력에서 제거한다. timeout, 프로세스 종료, disk full, lock contention, changed checkout, unavailable commit을 서로 구분한다. 실패를 PASS로 요약하지 않는다. 재개는 실제 검사 단계를 다시 실행할 뿐 LLM 대화 재개를 뜻하지 않는다.

## 호환성과 복구

기존 checker·proposal schema·Wiki 기록은 변경하지 않는다. 새 교환 manifest가 기존 checker 인자에 필요한 exact local proposal을 연결한다. checker를 바꿔야 한다면 커밋 권한 소유자가 새 기준 커밋을 먼저 보존하고 별도 구현 diff를 검증한다. runner 구현 diff에서 checker 기준을 수정하지 않는다.

실행 파일과 state는 분리한다. rollback은 runner 사용 중단이며 기존 patch knowledge 명령은 그대로 동작한다. state는 private 작업 폴더에 남겨 검사 근거를 보존하고 자동 삭제하지 않는다. checkout mutation을 하지 않는 초기 버전에는 source 복구 로직이 필요 없다.

## 작은 작업과 한 writer 경계

1. 새 `tools/patch_exchange.py`, 새 `tests/test_patch_exchange.py`, 새 `tests/fixtures/nf05/` 소유자가 manifest/path/hash/scope 검증과 inspect를 만든다.
2. 새 `tools/improvement_runner.py`, 새 `tests/test_improvement_runner.py` 소유자가 기존 checker 호출, lock·atomic state·history·중단 재개를 만든다. 1번 검증 결과 DTO만 받는다.
3. `skills/patch-knowledge/SKILL.md`, `docs/guide.md` 소유자가 명시적 CLI와 권한 경계·검사 기준 보존을 문서화한다. 이 구현에서는 `tools/patch_knowledge_check.py`와 기존 독립 인수 파일을 쓰기 소유하지 않는다.
4. 통합 담당자가 읽기 전용 fixture 저장소에서 실제 Git object 부재·dirty checkout·강제 중단·재개를 검증하고 필요한 CHANGELOG/Wiki 기록을 만든다. 커밋은 별도 권한이다.

## 인수와 검증

```sh
python3 -B -m unittest discover -s tests -p 'test_patch_knowledge.py'
python3 -B -m unittest discover -s tests -p 'test_patch_knowledge_check.py'
python3 tools/patch_knowledge.py verify --ref HEAD
```

새 검사 제안은 `python3 -B -m unittest discover -s tests -p 'test_patch_exchange.py'`와 `python3 -B -m unittest discover -s tests -p 'test_improvement_runner.py'`다. 악성 경로·symlink·과대 입력·tampered hash·없는 commit·checker mode 변경·같은 명령의 다른 blob·두 runner 동시 실행·각 atomic write 직전 중단·로그 중복·디스크 오류를 포함한다. 실제 fixture 커밋을 만든 테스트 내부에서 checker의 baseline 예상 실패와 target 통과를 재현하고 원본 checkout fingerprint 불변을 확인한다. 제품 checkout 커밋 권한을 테스트가 대신하지 않는다.

## Cursor 구현·테스트 프롬프트

```text
NF-05의 로컬 교환 inspect와 결정적 read-only 개선 검사 러너만 구현하라. patch_knowledge/check의 현재 schema와 frozen checker·검사 blob/mode 계약을 먼저 읽어라. 소유 파일은 작업 1~3과 필요한 CHANGELOG/Wiki다. 기존 checker/독립 검사 파일은 수정 금지이며 다른 dirty 작업을 보존한다. manifest의 임의 명령은 실행하지 말고 검토된 exact proposal과 고정 checker만 기존 gate에 전달하라. 초기 버전은 plain directory와 로컬 commit 확인, git apply --check preflight다. 자동 적용·fetch·commit·merge·push·공개 업로드·hook·Goal·CUA·LLM 지속 실행 주장은 금지한다. one writer lock·atomic state/history·실패 재개와 changed checkout 거절을 독립 검사로 입증하라. 기존/새 명령을 실행하고 실제 fixture 저장소에서 중단·재개를 확인하라. 권한이나 기준 commit이 없으면 needs-local-commit/blocked로 남겨라. 반환은 변경 파일, manifest/state 계약, frozen 기준 증거, 검사 결과와 미검증 위험이다.
```

# 삭제 전 보존한 별도 Git 계보

이 기록은 현재 canonical main의 조상 밖에 있었던 이전 개발·릴리스 계보다. 현재 릴리스 선언이나 새 설치 소스가 아니다. main을 checkout/reset하거나 삭제한 브랜치를 복원하지 않고, 보존 bundle을 임시 bare 저장소에서 읽어 조사했다.

## 조사 범위와 출처

보존 bundle의 SHA-256은 `69aac71126cd34c9a451e091e134aec80ca6a9d401485830567c2869e8017192`다. 실제 파일의 해시를 다시 계산해 일치를 확인했다. 원래 개인 보관 경로는 배포 기록에 넣지 않는다. 당시 보존한 head19개 중10개가 canonical 기준 밖에 있으며, 그 계보에서39개 추가 커밋을 확인했다. 현재 canonical43개와 합친 조사 범위는82개 고유 커밋이다. 현재 canonical 기준은 `0bd817701f3df66673e314007f768a6de404fd78`이다.

이전 계보의 마지막 head는 `bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a`이다. 그 조상39개를 모두 기록했고 merge도 포함했다. 최초 `f0e81fcca8e6bb3e44d90d1509a4830c189c3701`는 이미 만들어진0.16.1 제품의 기준선 반입이다. 이보다 앞선 개별 패치의 Git 원문은 이 자료에 없어 복원 완료로 표시하지 않는다.

## 현재 main과의 관계

이전0.18.1 head `bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a`와 canonical의 첫 구현 반입 `aa3acddf626642b7bf0db2f04730cab9cc533a4b`을 직접 Git으로 비교했다. 두 커밋의 전체 tree가 같다. 파일별 차이는0개다. 따라서 이전 수정은 canonical에서39개의 조상 커밋으로 이어지지 않았지만 동일한 최종 파일 상태로 일괄 이식됐다. 이를 미반영 기능39건이나 새 릴리스39개로 세지 않는다.

`release/0.18.1`이라는 보존 브랜치 이름과 공개 버전 태그 `v0.18.1`을 구별한다. 전자는 bce939d, 후자는 aa3acdd를 가리킨다. 버전명이 같다는 사실은 같은 커밋이라는 뜻이 아니다. canonical의 다음 변경들은 [일괄 반입 기록](../patches/aa3acddf626642b7bf0db2f04730cab9cc533a4b.md)과 [현재 버전 대조표](../releases.md)를 따른다.

## 무엇을 보완했는가

0.16.1 기준선 뒤의 시각 품질 관문·레이어 어휘·쓰기 전 일괄 검사·역할 토큰·오류 분류·읽기 전용 status·라이브 미리보기 분리와0.17.0 지침 정정을 개별 diff로 기록했다.0.17.1 버튼 대비,0.17.2 MIT,0.17.3 이미지 fit/캠페인별 ID,0.17.4 제작 가능한 그래프/키아트 문구,0.17.5 선택 그래프 확장,0.17.6 경로/variant radius,0.18.0 읽기 결과·신선도·이미지 경고·제공 디자인 시스템,0.18.1 공개 배포 정리도 보존했다. 병합은 같은 기능의 별도 구현으로 중복 계산하지 않는다.

[계보별 목록](index.md)과 `catalog.json`은 원래 head·부모·tree·파일 목록·diff 해시·당시 버전과 페이지 해시를 보존한다. 각 페이지는 실제 전후 동작·인터페이스·호환성·복구·검증 한계를 설명한다. 커밋 메시지의 테스트 성공 보고를 새 실행 통과로 옮기지 않는다.

## 검사하기

```sh
python3 tools/patch_knowledge_legacy.py verify --wiki docs/llm-wiki/legacy
```

일반 fork clone에 옛 Git 객체가 없으면 위 명령은 보존 기록의 구조·해시·필수 항목·커버리지·링크를 검사하고 `structural-only`로 보고한다. 원본 Git 검증으로 표현하지 않는다. bundle을 소유한 운영자는 임시 bare 저장소에서 읽기 전용으로 다음 명령을 실행해 실제 객체와 다시 대조한다.

```sh
python3 tools/patch_knowledge_legacy.py verify --wiki docs/llm-wiki/legacy --source-git <임시-bare-저장소>
```

현재 main을 변경하거나 브랜치를 복원할 필요는 없다. 원래 source capture에 쓴 커밋·bundle 해시·보존 head는 고정된 역사 자료다. 새로운 fork 패치는 현재 main의 카탈로그로 기록한다. 옛 bundle이 없는 환경의 실제 Git 검증은 미확인으로 남긴다.

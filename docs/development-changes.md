# 개발 중 Graph 변경 파악

Codex는 작업 중인 Git 변경을 기준 커밋, 스테이징 영역, 작업 트리에서 각각 읽는다. [릴리스 소유권 Graph](../release/authority.json)와 그 Graph에 등록된 하위 Graph 목록을 재사용한다. 예를 들어 `figma-bridge/assets`는 더 구체적인 산출물 경계이고, 그 밖의 `figma-bridge`는 Design 호스트 경계다.

```mermaid
flowchart LR
    G["Git 기준·스테이징·작업 트리"] --> O["리비전별 소유 Graph와 대조"]
    O --> R["변경 소유자·선언된 소비 영역·검사 후보"]
    O --> X["미매핑·검사 근거 없음"]
    P["선택한 로컬 패널 검사"] --> R
```

저장소 루트에서 실행한다. 기본 비교점은 `HEAD`이며 스테이징된 변경과 저장만 한 변경을 확인한다. 아직 공개하지 않은 커밋까지 포함하려면 현재 비교할 브랜치나 커밋을 `--base`에 지정한다.

```sh
python3 -B tools/development_changes.py --base HEAD
python3 -B tools/development_changes.py --base origin/main --inventory --json
python3 -B tools/development_changes.py --base HEAD --panel-tools
```

- `--inventory`는 현재 체크아웃에서 Git이 관리하거나 새로 발견한 비무시 파일의 경로를 소유 영역별로 분류한다. 소유권 정의가 바뀌면 파일 내용이 동일해도 영향을 표시한다. 삭제·이동 및 스테이징에만 남아 있는 파일은 해당 리비전의 소유 정보로 확인한다. `git add -N` 경로에는 추가 예정 표시가 붙고 스테이징된 내용은 표시되지 않는다.
- `--panel-tools`는 설치된 Biome·Oxlint·Knip을 기존 패널 설정으로 실행한다. 기본 리포트는 설정과 설치 상태만 표시한다. 패널 외 경로의 자동 검사 범위는 저장소 Graph에 선언된 검사와 각 파일에 등록된 근거에서 확인한다.
- `surface-declaration`은 영역에 선언된 검사다. `historical-candidates`는 기존 검증 기록에서 연결이 확인된 테스트다. 테스트나 증거 파일을 변경하면 이를 근거로 쓰는 영역과 파일도 표시한다. 후보의 현재 바이트를 기록된 해시와 대조하고 테스트가 바뀌었거나 증거를 확인할 수 없으면 `needs-review`로 표시한다. 사용자 동작의 인수는 [유지보수 검증](maintenance-verification.md)에서 직접 실행해 확인한다.
- 경로 소유권이 있어도 정본·검사 파일이 없거나 변경 경로에 연결된 검증 근거를 확인할 수 없으면 종료 코드 1을 반환한다. 미매핑 경로와 Git에서 숨긴 파일·서브모듈도 검토 대상이다. 분석 도중 Git 상태나 읽은 작업 트리 파일이 바뀌면 결과를 폐기한다.
- Git 객체는 로컬에서 읽는다. 부분 클론에서 필요한 객체가 없으면 분석 불가와 종료 코드 2를 반환한다. 필요한 객체는 사용자가 승인한 별도 Git 작업에서 확보한 뒤 다시 확인한다.

이 개발 명령은 경로와 근거를 읽어 출력한다. 실제 Figma 사용 중의 Graph 반영은 [라이브 변경 계약](../specs/live-change-sync/spec.md)에서 관리한다. 패널의 Graph 적합성과 생성물은 [기존 집계 검사](maintenance-verification.md#figma-패널-graph-검증)에서 별도로 확인한다.

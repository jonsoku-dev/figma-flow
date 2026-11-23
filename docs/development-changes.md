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

- `--inventory`는 현재 체크아웃에서 Git이 관리하거나 새로 발견한 비무시 파일의 경로를 소유 영역별로 분류한다. 소유권 정의가 바뀌면 파일 내용이 동일해도 영향을 표시한다. 삭제·이동 및 스테이징에만 남아 있는 파일은 해당 리비전의 소유 정보로 확인한다.
- `--panel-tools`는 설치된 Biome·Oxlint·Knip을 기존 패널 설정으로 실행한다. 기본 리포트는 설정과 설치 상태만 표시한다. 패널 외 경로의 자동 검사 범위는 저장소 Graph에 선언된 검사와 각 파일에 등록된 근거에서 확인한다.
- `surface-declaration`은 영역에 연결된 검사다. `historical-candidates`는 파일에 직접 연결된 기존 테스트 후보로 이름과 증거 위치를 함께 보여준다. 두 경우 모두 검사를 별도로 실행하기 전에는 현재 변경의 통과 근거가 없다. `no-file-witness`와 `no-surface-check`에서는 관련 기능의 테스트를 확인한다.
- 미매핑 경로나 Git에서 숨긴 파일·서브모듈은 따로 표시한다. 경로 판정은 `ownership-mapped`이며 제품·동작 인수 상태는 기존 [유지보수 검증](maintenance-verification.md)에서 결정한다. 검사나 경로 판정에 검토가 필요하면 종료 코드 1을 반환한다. 리포트를 만들 수 없는 입력 오류는 2를 반환한다.

이 개발 명령은 경로와 근거를 읽어 출력한다. 실제 Figma 사용 중의 Graph 반영은 [라이브 변경 계약](../specs/live-change-sync/spec.md)에서 관리한다. 패널의 Graph 적합성과 생성물은 [기존 집계 검사](maintenance-verification.md#figma-패널-graph-검증)에서 별도로 확인한다.

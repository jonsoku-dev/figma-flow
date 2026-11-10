# 개발과 릴리스

## 변경 검증

저장소 밖의 가상환경에 `requirements-optional.txt`를 설치합니다. Python 3.13, Node.js 26을 사용한 검사 명령입니다.

```sh
python -B -m unittest discover -s tests
node --test tests/*.cjs
python -B -m unittest discover -s examples/native-direction-review -p test_demo.py
```

검사 명령을 파이프로 연결하면 마지막 명령의 종료 코드만 보일 수 있습니다. 명령별 종료 코드와 skip 사유를 확인하세요. 깨끗한 클론에는 외부 캠페인의 회귀 레이아웃과 운영자가 제공하는 네이티브 읽기 자료가 없습니다. `FIGMA_DRAFT_LIVE_MANIFEST`와 `FIGMA_DRAFT_LIVE_READBACK`에 제공 권한이 있는 실제 시안 자료를 지정해 선택적 검사를 실행할 수 있습니다. 증거·실행 출력은 저장소 바깥에 둡니다.

## 버전과 GitHub Release

1. 호환되는 수정·문서는 패치, 호환되는 기능 추가는 마이너 버전을 올립니다. 호환성을 깨는 변경은 릴리스 노트에 영향과 이행 방법을 명시합니다. 코덱스·범용 매니페스트의 `version`, README의 설치 태그, `CHANGELOG.md`의 릴리스 번호를 함께 갱신합니다.
2. 변경을 커밋하고 최종 트리에서 위 검사를 실행합니다. 처음 설치하는 경로는 깨끗한 클론에서 워크숍 예제를 만들어 Figma용 `manifest.json`까지 검증합니다. 원격의 대상 브랜치와 공개할 Git 사용자 이메일을 확인합니다.
3. 통과한 `main` 커밋에 `vX.Y.Z`로 주석 태그를 만듭니다. `CHANGELOG.md`의 해당 항목을 Release 본문에 쓰고 테스트 범위와 남은 제한을 덧붙입니다. 기존 공개 태그와 파일은 보존하고 변경본에는 새 버전을 부여합니다.
4. 릴리스 ZIP과 체크섬은 저장소 밖에서 만듭니다. 다음은 태그가 `v0.18.1`인 예입니다.

```sh
TAG=v0.18.1
ASSET="figma-flow-plugin-${TAG#v}.zip"
git archive --format=zip --prefix=figma-flow-plugin/ --output="../$ASSET" "$TAG"
(cd .. && shasum -a 256 "$ASSET" > "$ASSET.sha256")
```

5. 대상 `main`과 태그만 푸시하고 GitHub Actions 결과를 확인합니다. GitHub Release에 ZIP과 체크섬을 첨부하고 다시 다운로드해 `shasum -a 256 -c 파일명.zip.sha256`으로 확인합니다. Linux에서는 `sha256sum -c`도 사용할 수 있습니다. 받은 ZIP을 풀면 코드와 매니페스트가 `figma-flow-plugin/` 아래에 있습니다.

## 이슈·PR

실패한 단계, 사용한 버전, 실행 명령, 종료 코드, 기대값과 관찰값을 함께 적어 주세요. Figma 화면은 등록, 가져오기, 읽기, 검증 중 어느 단계인지 표시해 주세요. 계정 정보, 실제 파일 키, 초대 링크, 원본 대화·선택 기록을 공개 이슈에 첨부하지 마세요.

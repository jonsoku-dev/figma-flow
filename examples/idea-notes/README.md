# 모음 로컬 예제

원 기획서(`brief.md`)와 실행 가능한 앱, 관계 그래프, 로컬 SSOT 바인딩, 실제 생성한 테스트 결과를 함께 제공한다. Figma 노드나 원격 설계 검증은 포함하지 않는다. 별도 패키지 설치가 필요 없다.

이 예제를 실행할 때는 작업할 새 디렉터리로 전체 묶음을 복사한다. 이후 명령은 복사한 디렉터리에서 실행한다. 새 출력은 원본 예제에 쓰지 않는다.

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory app
```

브라우저에서 `http://127.0.0.1:8765/`를 연다. IndexedDB 데이터는 해당 브라우저와 origin에만 저장된다. 포트를 바꾸면 다른 origin이 된다.

다른 터미널에서 복사본의 테스트 결과를 재생성한다 (Node.js 18 이상).

```sh
node --test --test-reporter=tap tests/app.test.cjs > evidence/node-tests.tap
```

플러그인 루트에서 아래 명령은 원본을 새 디렉터리로 복사하고 테스트·엄격한 로컬 그래프 검사·렌더링·스냅샷·변경 검사를 실행한다. 출력 디렉터리는 존재하지 않는 이름을 지정한다.

```sh
python3 tools/run_local.py --out ../idea-notes-run-001
```

이 명령은 Node 테스트를 새로 실행하고, 묶음의 브라우저 검증 기록과 앱 해시가 일치하는지 확인한다. 브라우저를 새로 조작하지 않는다. 그래프·스냅샷은 플러그인의 `tools/run_local.py`로 실행할 수 있다. 직접 실행한다면 설치된 `skills/figma-flow/scripts/graph.py`와 `ssot.py`의 경로를 지정한다. `bindings.json`의 경로는 묶음 내부 상대 경로이며 `visual` 권위를 의도적으로 제외한다. 스냅샷에는 `--scope local-only`를 사용한다.

`screen-spec.md`에 동작, 원 기획서와의 해석, 검증 한계를 기록했다. Node 결과는 테스트 대역을 이용한 자동 검증이다. `evidence/browser.json`은 실제 Chromium 데스크톱/모바일·키보드 진입·저장/실패 재시도·다중 탭 관찰과 정확한 앱 해시를 담는다. 전체 키보드 순회·스크린 리더·교차 브라우저 검증은 포함하지 않는다. 편집·삭제·계정·동기화·협업은 원 기획서 범위 밖이다.

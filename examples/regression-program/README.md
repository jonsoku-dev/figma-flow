# 회귀 프로그램 탐색용 앱

Atlas Workspace, Morrow Market, Paper Room은 계획된 다중 페이지 회귀의 로컬 fixture다. 제품 SSOT가 아니고, 릴리스가 아니며, 호스트 채팅 첨부 UX나 실제 Figma 읽기를 증명하지 않는다.

시드는 `20261111`이다. 결제, 메일, 계정 생성, 공개 발행은 없다. 모의 서버는 전달받은 JSON만 보고 상태 없는 응답을 돌려준다.

## 다시 실행

저장소 루트에서:

```sh
python3 examples/regression-program/catalog.py
python3 -B -m unittest tests.test_regression_program_inputs tests.test_regression_program_apps
node --test tests/test_regression_program_apps.cjs
python3 examples/regression-program/server/serve.py --port 8765
```

브라우저 확인은 `http://127.0.0.1:8765/atlas/sign-in`에서 한다. `?signed=1&workspace=northwind`를 붙이면 로그인과 작업 공간 선택을 건너뛴다. `?omit=html`은 HTML 목업 구간을 뺀다.

화면 모델 검사가 통과해도 두 viewport의 시각 검수, 실제 Figma getter, 독립 검수자의 비평이 끝난 것은 아니다.

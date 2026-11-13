# 실행 중인 웹 화면 측정

브라우저에서 허용한 화면을 실제로 연 다음, [캡처 함수](../tools/web_design_capture.js)를 그 페이지의 읽기 전용 평가 환경에서 실행한다. 사진 파일을 전송하거나 URL을 가져오는 기능은 이 함수에 없다. 입력 필드의 값·쿠키·스토리지·숨은 DOM은 읽지 않는다. 렌더링된 텍스트를 내보내므로 대상 화면과 노출될 문구를 먼저 확인한다.

예를 들어 로컬 브라우저 테스트의 Playwright `page`가 대상 페이지를 표시하고 있다면 다음 코드로 측정한다. 테스트 러너와 페이지의 파일 저장은 호출자가 담당한다.

```js
const { captureWebDesign } = require('./tools/web_design_capture.js');
const capture = await page.evaluate(captureWebDesign, {
  screenId: 'WEB-account',
  extent: 'document',
});
await require('node:fs/promises').writeFile('capture.json', JSON.stringify(capture), { flag: 'wx' });
```

`screenId`는 다시 측정해도 같은 화면을 찾을 수 있는 ID다. `extent: 'document'`는 현재 페이지의 문서 영역을, `'viewport'`는 현재 보이는 크기를 측정한다. 반응형 기준점과 로그인 상태가 다르면 서로 다른 화면 ID를 사용한다. 브라우저가 지연 로딩한 이미지나 움직이는 레이어는 측정 시점의 상태를 따른다.

산출물은 화면 크기, 실제 DOM 순서의 배경 프레임·편집 가능한 줄별 텍스트·컨트롤·단순 SVG, 부모 경로, 같은 출처 이미지 요청 목록, 누락 항목을 담는다. 폼 레이블과 placeholder는 서로 구분된다. 텍스트의 폰트 이름·크기·행 높이·무게·색은 브라우저 측정값이다. CSS `letter-spacing`이 계산된 픽셀 값이면 텍스트의 `letterSpacing`에 부호가 있는 숫자로 기록한다. CSS 값이 `normal`이면 필드를 생략한다. 그래프 검증과 해시로 고정된 native plan은 이 선택 필드를 그대로 보존한다. [`tests/test_web_design_tracking.py`](../tests/test_web_design_tracking.py)는 숫자 자간 보존과 normal 생략을 확인한다.

같은 `componentKey`의 텍스트 컴포넌트는 자간을 포함한 캡처 스타일과 배경·테두리·레이아웃이 같을 때만 main component를 공유한다. 자간이 다르면 별도 main을 사용한다. 인스턴스의 텍스트 override를 읽을 때는 Figma의 native range API가 반환한 `PIXELS` 단위와 숫자를 캡처값과 비교한다. 캡처값이 없으면 기본 native 자간을 유지하고 자간 readback을 요구하지 않는다. 제공한 자간을 native API에서 읽을 수 없거나 값이 다르면 화면 적용이 실패한다.

퍼센트 중심과 색 정지점을 갖는 CSS 방사형 그라디언트는 Figma에서 편집 가능한 채우기로 변환한다. CSS 마스크·필터·그림자, 다른 배경 효과, 비디오·canvas, 복잡한 SVG 및 외부 이미지는 별도 항목으로 표시한다. 1,500개 레이어를 초과하면 더 작은 범위를 선택해야 한다. 캡처는 원본 웹 앱이나 Figma 문서를 변경하지 않는다.

## Canvas 픽셀 보존

캡처 함수는 각 `<canvas>`의 실제 `width`·`height`, CSS 박스, device pixel ratio와 원본 PNG를 기록한다. 브라우저의 `canvas.toDataURL('image/png')`가 성공하면 그래프 생성기가 PNG 바이트를 해시로 고정하고 `sourceRole: "canvas"`인 래스터 레이어로 연결한다. 원본 canvas 픽셀에는 CSS mask, filter, opacity와 겹친 DOM 요소가 포함되지 않는다. 캡처가 보이지 않는 효과를 보고하면 Figma 비교 전에 해당 한계를 확인한다.

교차 출처 오염이나 브라우저 제한으로 원본 픽셀을 읽을 수 없다면, 같은 경로·뷰포트·스크롤 위치에서 만든 실제 페이지 스크린샷을 준비한다. 다음 명령은 측정된 canvas 경계만 자르고 새 캡처 파일을 만든다. 바깥 DOM은 복사하지 않으며, 스크린샷에 보이는 합성 픽셀만 사용한다.

```sh
python3 tools/web_design_canvas_crop.py \
  --capture capture.json --screenshot page.png --canvas-id el-128 \
  --screenshot-extent viewport --out capture-with-canvas.png.json
python3 tools/web_design_source.py --capture capture-with-canvas.png.json \
  --id account-app --title "Account app" --out account-graph.json
```

`--screenshot-extent`는 스크린샷이 viewport인지 전체 document인지 지정한다. viewport 캡처는 측정 파일에 기록된 스크롤 위치와 일치해야 한다. 원본 측정은 그대로 두고 새 캡처로 작업한다. 그래프 증거에는 `canvas.toDataURL` 또는 `user-supplied-screenshot-crop` 중 실제 픽셀 출처와 해당 PNG 해시가 기록된다.

## 편집 가능한 Figma 화면 만들기

1. 로컬 이미지가 있으면 캡처의 `origin`과 이미지별 `requestTarget`을 자산 목록과 대조한다. 자산 목록의 각 객체에는 이 두 값과 `path`, `mimeType`, `sha256`을 둔다. 경로의 기준은 생성할 그래프의 폴더다. PNG, JPEG, WebP 원본을 여기에 보관한다. 이미지가 없는 화면은 `--assets`를 생략할 수 있다.
2. 다음 명령으로 그래프와 작업 계획을 각각 새 파일로 만든다. `--preview-width 460`은 전체 화면 비율을 유지하는 Figma PNG 미리보기를 요청한다.
3. 등록된 Figma Flow에서 지정한 Design 페이지를 열고 해당 작업을 적용한다. 읽기 결과의 `web_design.screens`에서 생성된 프레임과 컴포넌트 연결, 글꼴 대체, 텍스트 폭 편차와 미리보기를 확인한다. 원본과 같은 그래프로 다시 실행해 프레임이 재사용되는지 확인할 수 있다.

```sh
python3 tools/web_design_source.py --capture capture.json --assets images.json \
  --id account-app --title "Account app" --out account-graph.json
python3 tools/native_edit.py web-design --graph account-graph.json \
  --file-key FILE_KEY --page-id PAGE_ID --preview-width 460 --out account-plan.json
python3 tools/figma_workspace.py prepare --workspace WORKSPACE --kind native-edit \
  --key account-signup --title "Account signup" --project "Account app" -- --plan account-plan.json
```

페이지를 다시 측정하면 그래프에도 새 해시가 생긴다. 작업이 만든 프레임에서 디자이너가 텍스트나 스타일을 편집하면 같은 그래프를 재적용해도 그 변경을 보존하고 충돌을 보고한다.

### 네이티브 raster 미리보기 제한

새 프레임에 이미지가 있거나 영상이 pinned poster fallback을 사용하면 첫 PNG 내보내기는 준비용으로 버리고 두 번째 결과를 미리보기로 사용한다. 재사용 프레임, 벡터 전용 프레임, native 영상 프레임은 한 번만 내보낸다. 준비용 내보내기를 포함한 전체 미리보기 흐름은 45초 안에 끝나야 한다.

`--preview-width` 요청값은 360~480픽셀 범위로 설정한다. 비율은 유지하며 Figma plan은 결과를 최대 5,000,000픽셀로 축소한다. 이 제한 때문에 긴 변이 요청값보다 작아질 수 있다. 한 작업의 미리보기 PNG 총량은 8 MB를 넘을 수 없다. 이 미리보기는 raster 검토본이다. native 텍스트와 벡터 편집성, 브라우저의 모든 CSS 효과나 글꼴 렌더링이 동일하다는 뜻은 아니다. [`tests/test_web_design_preview.cjs`](../tests/test_web_design_preview.cjs)는 새 이미지 화면의 준비용 내보내기와 재사용·벡터 화면의 단일 내보내기 정책을 확인한다. 실제 native 미리보기와 스타일 readback 결과는 [Web fidelity 0321 인수 기록](web-fidelity-0321.md)에서 확인한다.

## 경로와 반응형 화면

같은 경로라도 모바일과 데스크톱 캡처에 서로 다른 `screenId`를 부여한다. 각 주소를 실제로 열고 두 크기에서 콘텐츠를 스크롤한다. 홈으로 돌아와 폰트와 지연 로딩 이미지, 한 번 재생되는 등장 애니메이션이 안정된 후 캡처한다. 브라우저의 뷰포트와 문서 콘텐츠 폭은 스크롤바 때문에 다를 수 있다. 캡처는 두 값을 모두 기록한다.

```sh
python3 tools/web_design_source.py --responsive \
  --capture blog-mobile.json --capture blog-desktop.json --assets media-index.json \
  --id publication --title "Publication" --out publication.json
python3 tools/native_edit.py web-design --graph publication.json \
  --screen WEB-blog-mobile --screen WEB-blog-desktop --readback-scope screens \
  --file-key FILE_KEY --page-id PAGE_ID --preview-width 420 --out blog-plan.json
```

`--responsive`는 원본 경로에 측정된 각 뷰포트를 연결한다. 같은 주소와 뷰포트를 두 번 넣으면 거절한다. 그래프에는 최대 256개 화면을 보관할 수 있고, 한 네이티브 작업에는 최대 16개를 선택한다. `--readback-scope screens`를 사용하면 해당 화면과 하위 레이어만 읽어 다른 프로젝트가 있는 페이지에서도 작업별 결과를 비교할 수 있다.

효과와 영상 지원 범위, 실제 예제 페이지의 내보내기 결과는 [반응형 인수 기록](responsive-web-verification.md)에 있다.

뷰포트 캡처는 현재 스크롤 위치를 기준으로 캔버스 좌표를 저장한다. 문서 캡처에서 뷰포트 스크린샷을 자를 때만 기록된 스크롤 오프셋을 적용한다. 스크린샷에 캔버스를 가리는 내용이 있다면 그 내용도 잘라낸 이미지에 들어간다. 검토한 스크린샷에서 해당 영역을 확인하고 원본과 같은 좌표계의 이미지를 사용한다.

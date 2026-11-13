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

산출물은 화면 크기, 실제 DOM 순서의 배경 프레임·편집 가능한 줄별 텍스트·컨트롤·단순 SVG, 부모 경로, 같은 출처 이미지 요청 목록, 누락 항목을 담는다. 폼 레이블과 placeholder는 서로 구분된다. 텍스트의 폰트 이름·크기·행 높이·무게·색은 브라우저 측정값이다. CSS 그림자·그라디언트, 비디오·canvas, 복잡한 SVG 및 외부 이미지는 별도 항목으로 표시한다. 1,500개 레이어를 초과하면 더 작은 범위를 선택해야 한다. 캡처는 원본 웹 앱이나 Figma 문서를 변경하지 않는다.

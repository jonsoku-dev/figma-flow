# CSS를 통해 연결된 사진과 글꼴

[정상 사진·글꼴 예제](../positive-assets/README.md)의 같은 Coffee Notes 배치를 사용한다. 사진·OFL 글꼴·동작 파일은 복제하지 않고 기존 파일을 상대 경로로 연결한다. 원본·해시·라이선스는 그 예제의 `sources.json`과 `fonts/OFL.txt`를 따른다.

HTML은 `entry.css`만 스타일로 연결한다. `@import url()`이 기존 `page.css`의 `@font-face`와 WOFF2로 이어지고, 문자열 `@import`가 `media/photo.css`의 사진 URL로 이어진다. HTML의 사진 직접 참조와 글꼴 preload는 없다. 배경 사진은 `role="img"`와 한국어 대체 설명을 갖는다.

회귀 서버에서 `/html/css-assets/index.html`을 열고 데스크톱·모바일의 에세이→출처→에세이를 확인한다. 실제 글꼴 로딩과 사진 응답은 브라우저에서 확인한다. 입력 소비 기록의 root는 이 폴더만이 아니라 공유 자산이 들어 있는 `examples/regression-program`으로 정한다. CSS를 포함한 로컬 참조는 그 명시적 root 안에서만 따라간다. 입력 결과v3 이전 기록은 다시 준비한다.

이 예제는 선언된 로컬 CSS 의존성의 신선도와 사진·서체 전달을 검사한다. CSS cascade 전체 해석, 임의 HTML importer, 외부 자산 수집, Figma에 웹 글꼴 바이너리를 업로드하는 기능을 주장하지 않는다.

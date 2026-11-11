# 정상 사진·글꼴 입력

커피 사진과 Hahmlet 한글 가변 글꼴을 실제 파일로 연결한 로컬 회귀 fixture다. 원래 `atlas/linked`의 누락 자산 사례는 그대로 유지한다.

회귀 서버에서 `/html/positive-assets/index.html#read`를 연다. **사진과 서체 살펴보기 → 에세이로 돌아가기**로 왕복하며 `#credits` 직접 링크도 지원한다. 결제·로그인·전송은 없다.

`@font-face`와 font preload는 같은 WOFF2를 사용한다. 사진·CSS·JS·글꼴에는 버전 쿼리를 사용하므로 정상 로딩과 로컬 참조 추적을 함께 확인할 수 있다. 네이티브 제작은 실제 브라우저에서 관찰한 배치와 같은 사진/선언된 글꼴을 기존 authored-layout 경로에 연결한다. 임의 HTML/CSS importer나 Figma 글꼴 파일 업로드 기능은 아니다.

사진은 [Coffee cup seen from above](https://commons.wikimedia.org/wiki/File:Coffee_cup_seen_from_above.jpg), Pixel.la의 CC0 사진이다. Figma의 4,096px 제한 안에서 사용할 1,600×900 JPEG 축소본이다. 원본 해시·크기와 축소 방법을 `sources.json`에 보존한다. Hahmlet은 [Google Fonts의 원본](https://github.com/google/fonts/tree/main/ofl/hahmlet)을 WOFF2로 인코딩했다. [OFL 라이선스](fonts/OFL.txt)를 함께 보존한다. URL·원본 blob·파일 해시는 `sources.json`에 있다.

이 입력 자체는 브라우저/Figma 성공을 증명하지 않는다. 실제 실행 결과와 getter는 각 검증 run에서 별도로 보존한다.

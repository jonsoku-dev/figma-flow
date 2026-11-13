# 별도 Widget API SDK

Widget API 프로젝트는 Figma Flow 플러그인과 별도로 만든다. 샘플은
`figma.widget.useSyncedState`로 공유 카운트를 보관하고 `AutoLayout`을 클릭할 때
1씩 증가시킨다. 생성되는 manifest는 Design과 FigJam을 지원 대상으로 선언한다.
실제 에디터 삽입·협업 동기화는 별도 인수 검증이 필요하다.

## 생성과 빌드

현재 작업 폴더에서 기존 경로와 겹치지 않는 새 폴더를 지정한다.

```sh
python3 tools/figma_widget_project.py init ../my-widget
cd ../my-widget
npm install --ignore-scripts --no-audit --no-fund
npm run check
npm run build
```

Widget와 Plugin의 공식 타입 선언 및 MIT 라이선스가 `vendor/`에 복사된다.
컴파일러만 TypeScript 5.9.3으로 설치한다. 설치 후 `package-lock.json`을 보존하고
캐시가 준비된 환경에서 `npm ci --offline --ignore-scripts`를 사용할 수 있다.
별도의 번들러나 React 런타임은 필요하지 않다. JSX는 공식
`figma.widget.h` / `figma.widget.Fragment`로 컴파일된다.

신뢰하는 로컬 TypeScript 5.9.3을 이미 설치했다면 설치 없이 검사할 수 있다.
다음 명령은 Figma Flow 저장소 루트에서 실행한다.

```sh
python3 tools/figma_widget_project.py check ../my-widget --typescript /path/to/typescript/lib/tsc.js
python3 tools/figma_widget_project.py build ../my-widget --typescript /path/to/typescript/lib/tsc.js
```

CLI는 복사된 선언·라이선스·출처의 해시를 확인하고 고정된 컴파일 옵션을 사용한다.
기존 폴더를 덮어쓰지 않고 심볼릭 링크를 통한 프로젝트·출력 경로를 거절한다.
빌드는 로컬 파일을 만들며 Figma를 연결하거나 widget을 삽입하지 않는다.

## Figma 데스크톱에서 가져오기

1. Design 또는 FigJam 문서를 연다.
2. **Widgets → Development → New widget…**에서 새 widget을 만든다.
3. Figma가 만든 manifest의 `id`를 확인한다. 공식 필드명은 `id`이며
   `widgetId`가 아니다. 등록된 Figma Flow 플러그인의 ID는 재사용하지 않는다.
4. 생성 프로젝트의 `manifest.template.json`을 `manifest.json`으로 복사하고
   그 ID를 `id`에 넣는다. 이미 발급받았다면 처음부터 `init`의 `--widget-id`에
   숫자 ID를 전달하면 된다. 도구는 ID를 발급하거나 소유권을 확인하지 않는다.
5. `src/code.tsx`를 검토하고 빌드한 뒤 **Widgets → Development → Import widget
   from manifest…**에서 생성 프로젝트의 `manifest.json`을 선택한다.
6. Development 메뉴에서 widget을 삽입한다. 클릭으로 카운트가 증가하는지 확인한다.
   Design과 FigJam, 두 협업 클라이언트에서 각각 검증하기 전에는 런타임 통과로
   보고하지 않는다.

네트워크는 `allowedDomains: ["none"]`으로 막혀 있고 private/proposed API나
사용자 정보 권한을 켜지 않는다. manifest는 `containsWidget: true`,
`widgetApi: "1.0.0"`, `documentAccess: "dynamic-page"`를 사용한다.

공식 [설정 안내](https://developers.figma.com/docs/widgets/setup-guide/)와
[manifest 계약](https://developers.figma.com/docs/widgets/widget-manifest/)을 따른다.

## 오프라인 API 검색과 출처

```sh
python3 tools/figma_widget_project.py search useSyncedState --limit 0
python3 tools/figma_widget_project.py search AutoLayout
python3 tools/figma_widget_project.py verify
```

검색은 타입·멤버·JSDoc의 원문 행과 앞뒤 문맥, 고정 커밋의 링크를 반환한다.
AST 의미 분석이 아니므로 선언과 문서 예제가 함께 검색될 수 있다. 검색 결과는
API 구현률이나 실제 동작의 증거가 아니다. 검색·검사는 네트워크를 사용하지 않는다.

Widget 타입은 공식 [figma/widget-typings](https://github.com/figma/widget-typings/tree/8815555bab1cf358ee9958fe2fa2cf46f77f3fb6)
1.13.0을 고정한다. `library/figma-widget/source.json`은 커밋과 파일별 SHA-256을
기록하며 원문 선언·패키지 메타데이터·MIT 라이선스를 그대로 보존한다. Plugin API
타입은 별도 `library/figma-api/source.json`의 고정본을 함께 사용한다.

# Node.js 환경 설정

이 문서는 2026-11-10에 확인한 현재 LTS인 Node.js 26.13.0을 이 저장소에서 사용하고, 조직에서 요구하는 경우 사내 npm 레지스트리를 설정하는 방법을 안내합니다. 공식 [Node.js 다운로드 페이지](https://nodejs.org/en/download), [릴리스 일정](https://nodejs.org/en/about/previous-releases), [v26.13.0 릴리스 노트](https://nodejs.org/en/blog/release/v26.13.0)를 참고하세요. 이 저장소에는 npm 패키지와 의존성 정의가 없습니다. 여기서 `npm install`이나 `npm ci`를 실행하지 마세요.

## 설정 전에 레지스트리 정보를 확인하세요

사내 레지스트리는 회사마다 다릅니다. IT 또는 패키지 관리자에게 정확한 HTTPS 레지스트리 URL을 경로까지 포함해 요청하세요. 레지스트리가 모든 패키지를 제공하는지, `@company` 같은 특정 npm 스코프만 제공하는지도 확인하세요. 호스트, 경로, 스코프를 추측하지 마세요.

도메인만 전달받았다면 HTTPS 사용 여부와 필요한 서비스 경로를 확인해 전체 URL로 정리하세요. 경로를 임의로 덧붙이지 않습니다. URL은 HTTPS여야 하며 사용자 이름, 비밀번호, 쿼리, 프래그먼트를 포함하면 안 됩니다. 공백과 제어 문자도 포함하면 안 됩니다. `https://npm.example.internal/repository/npm/`은 URL 모양만 보여 주는 예시입니다. 실제 레지스트리 주소로 복사하지 마세요.

회사에서 레지스트리를 요구하지 않으면 레지스트리 설정을 건너뛰세요. 프로젝트 `.npmrc`는 `package-lock=false`만 설정합니다. 레지스트리를 지정하지 않으므로 기존 npm 레지스트리 설정을 바꾸지 않습니다.

## Node.js를 설치하고 선택하세요

### macOS와 Linux에서 nvm 사용

[공식 nvm README의 설치 및 업데이트 절차](https://github.com/nvm-sh/nvm#installing-and-updating)를 따라 nvm을 설치하세요. 새 터미널을 열거나 셸 설정을 다시 불러온 뒤, 저장소 루트에서 다음 명령을 실행하세요.

```sh
nvm install
nvm use
node --version
npm --version
```

`nvm install`과 `nvm use`는 `.nvmrc`에 기록된 버전을 읽습니다. 다음 단계로 가기 전에 `node --version`이 해당 버전을 출력하는지 확인하세요.

### Windows

Node.js 공식 설치 프로그램에서 `.nvmrc`에 기록된 버전을 설치하거나, `nvm-windows`를 설치한 뒤 `nvm install <version>`과 `nvm use <version>`을 실행하세요. `<version>`은 `.nvmrc`의 값을 `v` 없이 입력합니다. `nvm-windows`는 `.nvmrc`를 자동으로 읽지 않습니다.

## 레지스트리 URL을 확인하세요

Node.js를 선택한 뒤 Bash에서 실행하세요. 관리자에게 받은 URL을 입력합니다. 검사는 HTTPS가 아닌 URL, 사용자 정보, 쿼리, 프래그먼트, 줄바꿈을 거부합니다.

```sh
IFS= read -r -p '사내 npm 레지스트리 URL: ' REGISTRY_URL
node -e 'try { const raw = process.argv[1]; const u = new URL(raw); if (u.protocol !== "https:" || !u.hostname || u.username || u.password || raw.includes("?") || raw.includes("#") || /[\s\x00-\x1f\x7f]/.test(raw)) process.exit(1); } catch { process.exit(1); }' "$REGISTRY_URL" || { printf '%s\n' '잘못된 URL입니다. 관리자에게 받은 정확한 HTTPS URL을 입력하세요.' >&2; return 1 2>/dev/null || exit 1; }
```

관리자가 지정한 경로를 그대로 유지하세요. URL 파서는 형식을 확인하지만, 사내 레지스트리가 해당 경로를 받는지는 확인할 수 없습니다.

레지스트리가 특정 스코프만 제공하면 스코프도 입력하세요. 앞에 `@`를 붙입니다. 예를 들어 `@company`입니다. 전체 패키지 미러라면 비워 두세요.

```sh
IFS= read -r -p '레지스트리 스코프. 전체 패키지면 Enter: ' REGISTRY_SCOPE
case "$REGISTRY_SCOPE" in
  '') ;;
  @*) printf '%s\n' "$REGISTRY_SCOPE" | grep -Eq '^@[a-z0-9][a-z0-9._-]*$' || { printf '%s\n' '예를 들어 @company처럼 소문자 스코프를 입력하세요.' >&2; return 1 2>/dev/null || exit 1; } ;;
  *) printf '%s\n' '스코프는 @로 시작해야 합니다. 전체 패키지면 비워 두세요.' >&2; return 1 2>/dev/null || exit 1 ;;
esac
```

## 회사에서 요구할 때 프로젝트 레지스트리를 설정하세요

먼저 기존 프로젝트 및 사용자 설정을 확인하세요. 회사나 다른 프로젝트에 필요한 `.npmrc` 항목은 보존하세요.

```sh
npm config get package-lock
npm config get registry
npm config get userconfig
```

프로젝트 `.npmrc`는 Git이 추적합니다. `npm config set --location=project`는 이 파일을 수정합니다. 기존 키를 보존하고 변경 내용을 확인하세요. 회사 URL은 로컬 설정으로 유지하며, 회사 private 저장소에 공유할 때만 해당 저장소 정책에 따라 커밋합니다. 인증값은 항상 제외합니다. 파일 전체나 사용자 `.npmrc`를 로그에 출력하지 말고 다른 사용자의 파일을 복사하지 마세요.

변경 전 프로젝트 `.npmrc`를 저장소 밖의 사용자 전용 위치에 백업합니다. `npm config set`은 주석을 제거하거나 서식을 다시 쓸 수 있으므로, 주석이 필요하면 백업과 대조해 복원하거나 Codex가 필요한 키만 편집하도록 요청합니다. 백업에 인증값이 있을 수 있으므로 Git·공유 ZIP에 포함하지 않습니다.

회사의 레지스트리가 모든 패키지를 미러링하면 프로젝트 기본 레지스트리만 설정하세요.

```sh
npm config set --location=project registry "$REGISTRY_URL"
```

회사의 레지스트리가 특정 스코프만 제공하면 해당 스코프만 설정하세요.

```sh
npm config set --location=project "$REGISTRY_SCOPE:registry" "$REGISTRY_URL"
```

두 번째 명령은 스코프 밖 패키지의 기본 레지스트리를 유지합니다. 관리자가 미러와 스코프 레지스트리를 모두 요구한 경우에만 두 명령을 모두 실행하세요.

## 로그인하고 회사 인증서를 신뢰하도록 설정하세요

npm 사용자 설정으로 인증하세요. 스코프 레지스트리라면 로그인 명령에 스코프를 전달합니다. 전체 패키지 미러라면 `--scope`를 생략하세요.

```sh
npm login --registry="$REGISTRY_URL" --scope="$REGISTRY_SCOPE"
```

전체 패키지 미러라면 `npm login --registry="$REGISTRY_URL"`을 실행하세요. 로그인 프롬프트를 따르세요. 토큰, 비밀번호, 인증 값을 프로젝트 `.npmrc`, 저장소, 프롬프트, 명령 인자에 넣지 마세요. 자격 증명은 사용자 설정이나 회사가 승인한 자격 증명 도구에 보관하세요.

회사에서 사설 인증 기관을 사용하면 IT에 승인된 CA 파일을 요청하고 사용자 설정에 등록하세요.

```sh
npm config set cafile "/absolute/path/to/company-ca.pem" --location=user
```

`strict-ssl=false`를 설정하거나 TLS 검증을 끄지 마세요.

## 적용된 설정과 연결을 확인하세요

저장소 루트에서 실행하세요. `npm config get`은 현재 적용된 프로젝트 설정을 출력합니다. `npm ping`은 지정한 레지스트리에 접속하므로 네트워크와 인증이 필요할 수 있습니다.

```sh
npm config get package-lock
npm config get registry
npm ping --registry="$REGISTRY_URL"
```

스코프 레지스트리라면 스코프 설정도 확인하세요.

```sh
npm config get "$REGISTRY_SCOPE:registry"
npm ping --registry="$REGISTRY_URL"
```

회사에서 별도 레지스트리를 요구하지 않으면 ping 명령은 생략하고 `npm config get registry`로 기존 레지스트리를 확인하세요.

## lockfile을 GitHub에 올리지 않기

프로젝트 `.npmrc`는 npm 잠금 파일 생성을 끕니다. `.gitignore`는 어떤 디렉터리에 있든 npm, pnpm, Yarn, Bun 잠금 파일을 무시합니다. 이미 Git이 추적하는 잠금 파일은 ignore 규칙만으로 제거되거나 추적 해제되지 않습니다. 설정 과정에서 추적 중인 잠금 파일을 삭제하지 마세요.

추적 중인 파일과 커밋에 포함된 파일을 각각 확인합니다. 출력의 `blocks.py` 같은 일반 소스와 실제 패키지 매니저 lockfile은 구분하세요.

```sh
git ls-files '*lock*'
git diff --cached --name-only
git check-ignore -v package-lock.json app/package-lock.json pnpm-lock.yaml yarn.lock bun.lock bun.lockb
```

이미 추적 중인 lockfile이 있으면 그 **정확한 경로만** `git rm --cached -- "실제/경로/package-lock.json"`으로 추적 해제하고 변경을 확인합니다. `--cached`는 로컬 파일을 보존합니다. 전체 인덱스를 지웠다가 다시 추가하지 않습니다. 이 절차는 다음 커밋에서만 제외하며 과거 커밋까지 지우지는 않습니다. 과거 lockfile도 새 private 저장소에 전달하지 않으려면 [릴리스 스냅샷 복제](private-repository.md#3-권장-검증한-릴리스의-파일만-가져오기)를 사용하세요. npm의 `package-lock=false`는 pnpm·Yarn·Bun의 생성 옵션까지 제어하지 않으므로, 별도 앱에서 이 도구를 쓸 때도 생성 옵션과 Git 추적 여부를 따로 확인합니다.

이 저장소에는 루트 `package.json`과 npm 잠금 파일이 없습니다. `npm ci`에는 패키지 매니페스트와 잠금 파일이 필요하므로 여기에는 적용되지 않습니다. Node 기반 검사는 Node 내장 테스트 러너를 직접 사용합니다. 저장소 안내나 CI 워크플로의 명령을 사용하세요.

설치 오류만으로 사내 레지스트리가 원인이라고 단정하지 마세요. 오류 내용, 적용된 레지스트리, 인증, 인증서 설정, 회사의 패키지 정책을 확인한 뒤 설정을 바꾸세요.

이 저장소에서는 사용자 운영 정책에 따라 lockfile을 GitHub에 올리지 않습니다. 커스텀 레지스트리로 만든 lockfile이 이전 레지스트리의 URL을 유지하는 경우는 [npm의 레지스트리 문서](https://docs.npmjs.com/cli/v7/using-npm/registry/)에도 설명되어 있습니다. lockfile을 제외하면 새 설치 시 간접 의존성의 해석 결과가 달라질 수 있으므로 실제 Node/npm 버전과 검사 결과를 릴리스 검증에 남깁니다.

설정의 공식 근거: [npmrc와 인증 범위](https://docs.npmjs.com/files/npmrc/), [npm config의 package-lock·registry 설정](https://docs.npmjs.com/cli/using-npm/config/).

## 설정 전에 Codex에 확인을 요청하세요

Codex에 이 체크아웃의 npm 설정을 맡길 때는 명령 실행 전에 다음 프롬프트를 사용하세요.

> npm 설정을 바꾸기 전에 우리 조직이 사설 npm 레지스트리를 요구하는지 나에게 물어봐. 필요하다면 전체 경로를 포함한 정확한 HTTPS URL과 전체 패키지 미러인지 특정 `@scope`만 제공하는지 물어봐. 호스트, 경로, 스코프를 추측하지 마. URL에 사용자 정보, 쿼리, 프래그먼트, 줄바꿈이 없는지 확인해. 기존 프로젝트 `.npmrc`를 살펴보고 항목을 보존해. 필요한 프로젝트 레지스트리만 `npm config set --location=project`로 설정해. 인증 토큰이나 비밀번호를 프로젝트나 저장소에 쓰지 마. 인증은 내 사용자 설정이나 승인된 자격 증명 도구에 둬. TLS 검증을 끄지 마. `.npmrc` diff를 보여 주고 제공된 URL에 `npm config get`과 `npm ping`을 실행해. 루트 `package.json`과 npm 잠금 파일이 없으므로 `npm install`이나 `npm ci`를 실행하지 마. 레지스트리 설정이나 자격 증명을 커밋하지 마.

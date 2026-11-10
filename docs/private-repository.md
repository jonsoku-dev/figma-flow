# Private 저장소에서 Figma Flow 배포하기

이 문서는 공개 Figma Flow를 회사의 독립된 private 저장소로 복제하고, 그 저장소에서 Codex 플러그인을 설치·업데이트하는 절차입니다. 실제 원격 생성이나 업로드는 이 문서를 읽는 것만으로 실행되지 않습니다. 설치만 하려면 [설치·연동·업데이트](installation-and-updates.md)부터 진행하세요.

## 1. 배포 구조 결정

공개 저장소의 GitHub **Fork**는 공개입니다. private 배포에는 별도의 빈 private 저장소를 만듭니다. GitHub가 설명하는 [fork 공개 범위](https://docs.github.com/en/pull-requests/reference/forks)를 확인하세요.

| 항목 | 회사 배포에서 사용할 값 |
|---|---|
| GitHub 저장소 | 예: `acme/figma-flow-private` |
| 저장소 공개 범위 | `PRIVATE` |
| 플러그인 이름 | 기존 `figma-flow` 유지 |
| 마켓플레이스 이름 | 예: `acme-figma-flow-private`로 구분 |
| 설치 선택자 | `figma-flow@acme-figma-flow-private` |
| 배포 버전 | 검증한 태그 또는 정확한 커밋으로 고정 |
| npm 레지스트리 | 회사가 알려 준 실제 URL·경로와 적용 스코프 |
| Figma 개발 플러그인 ID | 각 프로젝트의 검토용·본제작용으로 별도 관리 |

마켓플레이스 이름은 `.agents/plugins/marketplace.json`의 최상위 `name`입니다. 회사 저장소와 원본의 이름을 구분하면 개인 설치와 회사 설치가 같은 소스로 오인되는 것을 줄일 수 있습니다. `source.path`는 저장소 루트를 기준으로 하는 `./`를 유지합니다. `.codex-plugin/plugin.json`의 `name`까지 바꿀 필요는 없습니다. `ON_INSTALL`은 설치 정책이며 GitHub 권한이나 Figma 로그인을 대신하지 않습니다. [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins)

## 2. 준비할 정보

Codex에 회사 GitHub 소유자/조직, 새 저장소 이름, 가져올 릴리스, 로컬 작업 폴더를 알려 주세요. 회사 npm을 쓴다면 도메인만으로 서비스 경로를 추측하지 말고 담당자가 제공한 전체 레지스트리 URL을 받습니다. `@acme`만 회사 npm을 쓰는지, 공개 패키지까지 회사 미러를 거치는지도 확인합니다. [npm 설정](npm-environment.md)

각 사용자에게 private 저장소 읽기 권한이 필요합니다. GitHub 조직이 요구하는 SSO·접근 승인과 SSH 또는 Git credential manager 설정을 완료합니다. `gh` 로그인과 Git의 HTTPS/SSH 인증은 별개일 수 있으므로 실제 설치에 쓸 URL로 `git ls-remote`를 확인합니다. 비밀번호·PAT·npm 토큰은 프롬프트, URL, 프로젝트 `.npmrc`에 넣지 않습니다.

```sh
gh auth status
git --version
codex --version
codex plugin marketplace add --help
```

## 3. 권장: 검증한 릴리스의 파일만 가져오기

새 저장소에 과거의 브랜치·태그·실험 파일을 모두 올릴 필요가 없다면 **릴리스 스냅샷**을 사용합니다. 원본의 Git 이력을 새 저장소로 복사하지 않으므로, 과거 lockfile이나 불필요한 파일이 따라가는지도 구분할 수 있습니다. MIT `LICENSE`와 저작권 고지는 유지합니다.

다음은 macOS/Linux의 새 폴더 예제입니다. `TAG`는 실제 확인한 릴리스 태그로 교체하고, 두 디렉터리는 기존 작업이 없는 새 경로를 씁니다. Windows에서는 Codex가 같은 동작을 PowerShell과 실제 경로에 맞춰 수행하게 하세요.

```sh
UPSTREAM=https://github.com/jonsoku-dev/figma-flow.git
TAG=vX.Y.Z
PRIVATE_REPO=acme/figma-flow-private
SOURCE_DIR="$PWD/figma-flow-upstream-release"
PRIVATE_DIR="$PWD/figma-flow-private"

git clone --branch "$TAG" --single-branch "$UPSTREAM" "$SOURCE_DIR"
git -C "$SOURCE_DIR" describe --tags --exact-match
git -C "$SOURCE_DIR" rev-parse HEAD
mkdir "$PRIVATE_DIR"
git -C "$SOURCE_DIR" archive --format=tar --output="$PRIVATE_DIR/source.tar" HEAD
tar -xf "$PRIVATE_DIR/source.tar" -C "$PRIVATE_DIR"
rm "$PRIVATE_DIR/source.tar"
cd "$PRIVATE_DIR"
git init -b main
```

`source.tar` 삭제는 방금 생성한 임시 아카이브만 대상으로 합니다. 생성된 파일을 확인하고 다음을 반영합니다.

1. `.agents/plugins/marketplace.json`의 최상위 `name`을 회사 고유 이름으로 변경합니다. 아래 예시는 그 한 필드만 바꿉니다.
2. [npm 설정](npm-environment.md)대로 `.npmrc`, `.nvmrc`, `.gitignore`를 확인합니다. `.npmrc`에는 인증값 없이 `package-lock=false`를 유지합니다. 회사 URL을 커밋할지는 private 저장소 운영 정책에 맞춥니다.
3. 가져온 원본 URL·태그·정확한 커밋을 `UPSTREAM.md` 등에 기록합니다. 플러그인을 수정한 회사 릴리스는 기존 태그를 덮어쓰지 말고 새 버전을 부여합니다.

```sh
python3 - <<'PY'
import json
from pathlib import Path
p = Path('.agents/plugins/marketplace.json')
data = json.loads(p.read_text())
data['name'] = 'acme-figma-flow-private'
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
PY
```

저장소에 올릴 파일과 lockfile 제외를 확인합니다. `.gitignore`는 이미 추적한 파일을 제외하지 않으므로 [추적 중인 lockfile 처리](npm-environment.md#lockfile을-github에-올리지-않기)도 확인하세요. `.npmrc`의 회사 도메인 외에 인증 토큰·사내 파일·실제 Figma 읽기 결과·선택 대화 기록이 포함되지 않아야 합니다.

```sh
git add .
git diff --cached --stat
git diff --cached -- .npmrc .nvmrc .gitignore .agents/plugins/marketplace.json
git ls-files '*lock*'
```

`*lock*`는 이름 후보를 넓게 찾는 조회입니다. `blocks.py` 같은 일반 소스까지 삭제하거나 추적 해제하지 않습니다. 패키지 매니저 lockfile은 하나도 추적하지 않아야 합니다. 실제 검사 명령은 [개발 가이드](../CONTRIBUTING.md)의 현재 명령을 사용하고, 명령별 종료 코드를 기록합니다. 준비가 끝난 뒤 초기 커밋을 만듭니다.

```sh
git commit -m "Import reviewed Figma Flow release"
```

**다음 블록은 원격 저장소 생성과 업로드입니다.** 실제로 회사 소유자·이름·private 범위를 지정해 실행을 요청한 경우에만 수행합니다. 이미 저장소가 있으면 새로 만들지 말고 공개 범위와 빈 저장소 여부부터 확인합니다.

```sh
gh repo create "$PRIVATE_REPO" --private
gh repo view "$PRIVATE_REPO" --json nameWithOwner,visibility,url
git remote add origin "https://github.com/$PRIVATE_REPO.git"
git remote -v
git push -u origin main
```

조회 결과가 `PRIVATE`가 아니면 업로드를 중단합니다. 기존 저장소에 강제 push하거나 `--mirror`로 덮어쓰지 않습니다. 커밋 검증이 끝나면 회사 릴리스 태그와 GitHub Release를 별도로 만듭니다. 공개 저장소에 회사 설정을 역으로 push하지 않도록 `origin`을 매번 확인하세요.

## 4. 원본 Git 이력도 보존해야 한다면

새 전용 클론에서 원본 `origin`을 `upstream`으로 바꾸고 회사 private 저장소를 `origin`으로 등록할 수 있습니다. 기존 개발자의 작업 클론은 그대로 둡니다. [GitHub의 저장소 복제 안내](https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository)는 전체 미러 방법도 설명합니다.

이 프로젝트의 일반 배포에는 전체 미러가 필요하지 않습니다. 과거 이력의 lockfile·인증값·배포 불가 에셋과 LFS 객체를 검토한 뒤 필요한 브랜치와 태그만 명시해서 push합니다. 과거 lockfile까지 GitHub에 올리지 않아야 한다면 3절의 스냅샷 방식을 사용하세요. 현재 `.gitignore`만 바꿔도 과거 커밋이 없어지는 것은 아닙니다. 이력 재작성은 별도로 승인·검토할 작업입니다.

## 5. 팀원이 private 저장소에서 설치하기

### 로컬 클론 방식: 인증과 경로를 확인하기 쉬운 기본 경로

팀원은 먼저 자신의 Git 인증으로 회사 저장소를 읽습니다. 설치할 태그가 회사 저장소에도 실제로 존재해야 합니다. 원본 저장소의 태그가 자동으로 회사 저장소에 생기지는 않습니다.

```sh
git ls-remote https://github.com/acme/figma-flow-private.git
git clone --branch vCOMPANY_VERSION https://github.com/acme/figma-flow-private.git
cd figma-flow-private
codex plugin marketplace list --json
codex plugin marketplace add "$PWD" --json
codex plugin add figma-flow@acme-figma-flow-private --json
codex plugin list --marketplace acme-figma-flow-private --json
```

설치 결과의 `installedPath`와 목록의 `version`, `installed`, `enabled`, `marketplaceSource`를 확인합니다. 이름만 같은 다른 원본이면 성공으로 취급하지 않습니다. 설치한 복사본의 `skills/figma-plugin-setup/SKILL.md`가 새 채팅에서 보이면 아래처럼 요청합니다.

```text
$figma-plugin-setup 회사 private 저장소에서 설치한 Figma Flow를 연동해 줘.
대상은 acme/figma-flow-private의 [회사 릴리스 태그], 마켓플레이스는 acme-figma-flow-private야.
Computer Use는 [가능/불가능]해. npm 레지스트리는 실제 설치 전에 내게 URL과 적용 스코프를 물어봐.
설치된 버전과 경로를 검증하고, 새 연습 파일에서 실제 Figma 결과 JSON을 읽어 검증해 줘.
```

첫 설치 때는 아직 스킬이 없으므로 [처음부터 맡기는 프롬프트](installation-and-updates.md#1-클론-전부터-codex에-맡기기)를 사용합니다.

### Git 마켓플레이스 직접 등록: 선택 경로

설치 머신의 Git 인증으로 해당 URL을 읽을 수 있으면 다음 방식도 사용할 수 있습니다. 지원 문법은 현재 `--help`로 확인합니다. 회사가 SSH를 허용하고 키가 설정된 경우 SSH URL도 쓸 수 있습니다.

```sh
codex plugin marketplace add https://github.com/acme/figma-flow-private.git --ref vCOMPANY_VERSION --json
codex plugin add figma-flow@acme-figma-flow-private --json
```

GitHub 커넥터에 연결된 계정이 로컬 Git 인증까지 제공한다고 가정하지 않습니다. 실패하면 토큰을 URL에 넣지 말고 로컬 클론 방식으로 진단합니다. 관리자용 workspace import는 조직 정책·권한이 별도인 경로입니다. [OpenAI의 private 저장소 import 안내](https://learn.chatgpt.com/docs/enterprise/plugin-management)

## 6. Computer Use가 없어도 같은 경로 사용

저장소 복제·설정·Codex 설치·패키지 생성·JSON 검증은 Computer Use 없이 CLI와 파일로 진행합니다. Figma Desktop의 새 개발 플러그인 생성, 매니페스트 가져오기, 실행, 결과 저장은 사용자가 합니다. [수동 조작 단계](installation-and-updates.md#4-computer-use가-없는-경우의-figma-조작)는 첫 설치와 업데이트 모두 같은 검증 기준을 사용합니다. private 저장소를 공개하거나 Figma 목적지를 HTML로 변경할 필요가 없습니다.

## 7. 회사 복제본 최신화

원본 최신 릴리스 → 회사 코드와 병합·검사 → 회사 릴리스 → 팀원 Codex 설치 갱신 → 각 프로젝트의 Figma 패키지 재생성·읽기 검증 순서입니다. 원본의 `main`을 모든 팀원에게 곧바로 배포하지 않습니다. 회사 스냅샷은 원본과 Git 이력을 공유하지 않으므로 `git merge upstream/main` 대신 새 원본 스냅샷과 회사 변경을 비교해 반영합니다. 이력 보존 방식은 별도 브랜치에서 병합합니다.

같은 이름으로 등록한 Git 마켓플레이스의 `upgrade`는 **마켓플레이스 소스**를 새로 읽는 명령입니다. 고정 태그를 다음 태그로 바꾸거나 이미 설치한 플러그인의 캐시까지 자동 교체했다고 판단하지 마세요. [Codex·Figma·선택적 동기화의 업데이트 절차](installation-and-updates.md#6-업데이트와-되돌리기)를 따릅니다.

## Codex에 private 복제 자체를 맡기는 프롬프트

```text
공개 Figma Flow의 [검증한 태그/커밋]을 [회사 조직/새 저장소 이름]의 독립된 private 저장소로 옮길 준비를 해 줘.
docs/private-repository.md를 읽고 기존 클론·원격·설치를 보존하며 새 전용 폴더에서 릴리스 스냅샷 방식으로 준비해.
마켓플레이스 이름은 [회사 고유 이름], 플러그인 이름은 figma-flow를 유지해.
회사 npm의 레지스트리 URL과 전체 미러/스코프 적용 방식을 먼저 물어봐. .nvmrc는 공식 자료로 확인한 현재 LTS의 정확한 버전을 써.
lockfile은 생성·커밋·업로드하지 말고, LICENSE와 출처는 보존해. 인증값과 Figma 실제 프로젝트 자료를 포함하지 마.
로컬 검증과 업로드할 파일 목록, 원격 이름과 PRIVATE 확인 방법까지 준비해.
실제 원격 생성·push는 준비 결과를 보여 준 뒤 내 지시를 받아. 이 작업의 범위는 로컬 준비까지야.
```

처음부터 실제 생성·업로드도 맡기려면 마지막 문장을 “`[조직/저장소]`를 **private**으로 생성하고 준비한 `main`을 push해도 돼. push 직전에 실제 원격과 `PRIVATE`를 확인해.”로 바꿉니다. 원격 대상과 권한은 현재 사용자의 지시에서 받아야 합니다.

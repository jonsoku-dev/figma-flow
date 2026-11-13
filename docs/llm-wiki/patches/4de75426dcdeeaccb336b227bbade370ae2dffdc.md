<!-- patch-knowledge
{"commit":"4de75426dcdeeaccb336b227bbade370ae2dffdc","diff_sha256":"27f005d5b0fd51db21f1ca30c070ebafd631927cbd4763193cd04cd688d52e39","files":[".codex-plugin/plugin.json","README.md","docs/guide.md","plugin.json"],"parents":["1430fdfbed0cc7862ff2bbf9648c2faf468cf3de"],"subject":"release: prepare Figma Flow 0.32.1 and update installation examples","tree":"fcb94ba005b5b320bd5b0b286109e1f9402c520e","versions":[{"path":"plugin.json","version":"0.32.1"},{"path":".codex-plugin/plugin.json","version":"0.32.1"}]}
-->

# release: prepare Figma Flow 0.32.1 and update installation examples

## 문제와 계기

이 두 수정 사항을 설치 시점에 구별할 버전이 필요했다.

## 결과 동작

Codex 플러그인 버전을 0.32.1로 올리고 한국어·영어·일본어 설치 예제를 일치시켰다.

## 변경 파일과 인터페이스

plugin.json 및 .codex-plugin/plugin.json의 version, README.md 및 docs/guide.md의 설치 예제를 바꿨다.

## 설계 이유와 출처

공개 설치 안내와 실제 로딩 버전을 분리해 검증하기 위해 동일한 버전 문자열을 사용한다.

## 호환성·이관·복구

0.32.0 설치 폴더와 원본 Figma 파일을 보존한다. 오래된 웹 캡처에는 자간 필드가 필수가 아니다.

## 검증과 미검증

두 manifest가 같은 0.32.1인지 대조했다. 패키지 변경과 별도로 태그·원격 파일·설치 경로 검증을 수행한다.

## 한계와 후속 개선

이 커밋 자체는 배포 파일의 존재나 실제 플러그인 로딩의 증거가 아니다.

## 관련 기록

[설치 가이드](../../guide.md) · [배포 기록](../releases.md#v0.32.1).

원문 대조는 `git show 4de75426dcdeeaccb336b227bbade370ae2dffdc`로 한다.

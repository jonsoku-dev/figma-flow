<!-- patch-knowledge
{"commit":"bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a","diff_sha256":"aead907247c3a8094ce3df840e0df3c401bdec9eabd221909a3d49877c250ec8","files":[".codex-plugin/plugin.json",".github/workflows/test.yml",".gitignore","CHANGELOG.md","CONTRIBUTING.md","README.md","docs/codex-setup-prompts.md","docs/design-system-trials.md","docs/figma-guide.md","docs/images/custom-ui-template.png","docs/images/development-menu.png","docs/images/draft-readback-save.png","docs/images/finished-preview.jpg","docs/images/manifest-picker.png","docs/images/new-plugin-dialog.png","docs/images/production-plugin-actions.png","docs/trials/mui-comparison.jpg","docs/trials/shadcn-comparison.jpg","plugin.json","requirements-optional.txt","skills/figma-flow/references/design-review.md","skills/figma-flow/references/local-design-audit.md","tests/test_figma_draft.py","tools/figma_draft.py"],"parents":["738b84b96cb51b3fafc5ef2667409ca189b90652"],"subject":"Prepare public release documentation and portable setup for 0.18.1","tree":"ce61009f41c024b1c03586582c6db3aae6d45ba7","versions":[{"path":"plugin.json","version":"0.18.1"},{"path":".codex-plugin/plugin.json","version":"0.18.1"}]}
-->
# bce939d · 0.18.1 공개 문서·portable setup

- 커밋: `bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a`
- 원문 제목: Prepare public release documentation and portable setup for 0.18.1
- 계보 유형: 일반 커밋; 이 문서는 역사적 계보 기록이며 현행 릴리스 선언이 아니다.

## 문제와 계기

공개 배포 준비에 사용자 안내, 기여 절차, CI와 portable setup 문서가 필요했고 embedded image 제한도 점검 대상이었다.

## 결과 동작

GitHub test workflow와 ignore 규칙, CHANGELOG/CONTRIBUTING, Codex setup prompts, Figma guide 및 trial 문서를 추가한다. 이미지 크기 검사도 figma_draft에 반영하며 manifest 버전을 0.18.1로 올린다.

## 변경 파일과 인터페이스

`.codex-plugin/plugin.json`, `.github/workflows/test.yml`, `.gitignore`, `CHANGELOG.md`, `CONTRIBUTING.md`, `README.md`, `docs/codex-setup-prompts.md`, `docs/design-system-trials.md`, `docs/figma-guide.md`, `docs/images/custom-ui-template.png`, `docs/images/development-menu.png`, `docs/images/draft-readback-save.png`, `docs/images/finished-preview.jpg`, `docs/images/manifest-picker.png`, `docs/images/new-plugin-dialog.png`, `docs/images/production-plugin-actions.png`, `docs/trials/mui-comparison.jpg`, `docs/trials/shadcn-comparison.jpg`, `plugin.json`, `requirements-optional.txt`, `skills/figma-flow/references/design-review.md`, `skills/figma-flow/references/local-design-audit.md`, `tests/test_figma_draft.py`, `tools/figma_draft.py`

## 설계 이유와 출처

설치·기여 안내와 자동 테스트의 출발점을 저장소에 제공하고, 개인 경로를 공유 설정에 고정하지 않는 portable setup 지침을 둔다.

## 호환성·이관·복구

새 CI workflow가 실행 조건을 정의하고 문서/이미지 자산이 추가되며 초과 embedded image는 거부될 수 있다.

## 검증과 미검증

test workflow와 관련 테스트 존재를 확인했으나 workflow 실행, 공개 게시, 실제 설치는 확인하지 않았다.

## 한계와 후속 개선

문서 추가는 공개 릴리스 완료나 CI branch protection을 뜻하지 않는다. 이미지 가이드 스크린샷의 현재 UI 적합성 미검증.

## 관련 기록

README/CHANGELOG, .github/workflows/test.yml, docs, tools/figma_draft.py, tests 및 manifests. 원본 Git 커밋 `bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a`; source bundle SHA-256 `69aac71126cd34c9a451e091e134aec80ca6a9d401485830567c2869e8017192`.

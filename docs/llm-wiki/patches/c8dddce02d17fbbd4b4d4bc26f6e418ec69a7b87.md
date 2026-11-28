<!-- patch-knowledge
{"commit":"c8dddce02d17fbbd4b4d4bc26f6e418ec69a7b87","diff_sha256":"b03588f98c4c0f9aec48b99af83456dc8c3698784dfcd07203f282ef0165d2b2","files":["CHANGELOG.md","docs/llm-wiki/catalog.json","docs/llm-wiki/patches/0e01fe1ded1cdcd3623a5bcba905027d9c953b1b.md","docs/llm-wiki/patches/319ccb58a5ecd7725a855d4e579513f35624025a.md","docs/llm-wiki/patches/5218dfe91cec6f19d8714800bb37043624f84b3c.md","docs/llm-wiki/patches/5a23f947043e5721f3ff849c46400691f45193f0.md","docs/llm-wiki/patches/d0a5c9fdbc21ccc6d4c20470cff79387427e50af.md","docs/llm-wiki/releases.md"],"parents":["319ccb58a5ecd7725a855d4e579513f35624025a"],"subject":"docs: freeze RC3 after all four direct verification paths","tree":"221d9eb0ded5e4a05486ce954e892d937347083c","versions":[{"path":"plugin.json","version":"1.1.0"},{"path":".codex-plugin/plugin.json","version":"1.1.0"}]}
-->

# 직접 검증기의 격리 결과 동결

커밋 `c8dddce02d17fbbd4b4d4bc26f6e418ec69a7b87`

## 문제와 계기

명명된 Node 계약을 포함한 네 직접 진입점의 격리와 정리 근거를 릴리스 기록에 연결했다.

## 결과 동작

버전 대조표에 직접 진입점별 수정, 기준 검사와 로컬 수락 범위가 남았다.

## 변경 파일과 인터페이스

부모 제품 커밋 이후 `CHANGELOG.md`와 `docs/llm-wiki/releases.md`에 변경을 기록하고 `docs/llm-wiki/catalog.json` 및 개별 패치 페이지에 근거를 연결했다.

## 설계 이유와 출처

제품 실행과 기록 동결은 서로 다른 커밋이므로 Git의 부모 대비 변경 경로를 확인했다.

## 호환성·이관·복구

당시 실행한 실제 Figma 선택·왕복 및 복원 근거를 그대로 보존했다.

## 검증과 미검증

네 실제 자식 경로는 전용 설정과 정리를 통과했다. 후속 release profile에서 독립 Python의 패키지 import 실패를 발견했다.

## 한계와 후속 개선

여러 검사를 한 인터프리터에서 호출하면 이전 검사에서 추가한 경로가 누락된 import를 가릴 수 있다.

## 관련 기록

[독립 import 검증](a24adcc9b6a7930702e82eb4d7d439f84f601aa3.md)과 [네 직접 경로](319ccb58a5ecd7725a855d4e579513f35624025a.md).

# 보존 head와 패치 목록

이 목록은 실제 보존 head19개와 canonical 밖 커밋39개를 전체 대조한다. [조사 방법과 동일 tree 이식 근거](README.md)를 함께 읽는다.

## 보존한 head

| 원래 head | 커밋 | canonical 관계 |
| --- | --- | --- |
| `codex/browser-access-unslop` | [1f8d203](../patches/1f8d203dff972a1c98b8b2a49d5d0d20a838d80e.md) | 현재 기준의 조상 |
| `codex/bundled-design-skills` | [0173535](../patches/01735351c2d82f1372442192b9bf14fa6f049a74.md) | 현재 기준의 조상 |
| `codex/remove-music-taste` | [a787647](../patches/a787647678eb3d8369bbdc9930a18b90427ed122.md) | 현재 기준의 조상 |
| `codex/skill-dependency-runtime` | [b27dffc](../patches/b27dffc2e923347831d30368faaf8136f2cc3b54.md) | 현재 기준의 조상 |
| `feat/readable-graph-specs` | [61c0b1e](../patches/61c0b1ea79abda7b258459e245a1187e1ecc0314.md) | 현재 기준의 조상 |
| `feature/graph-ssot-roundtrip` | [bf04926](../patches/bf049266356987b6abbf62533a5d3b0f9c549b8b.md) | 현재 기준의 조상 |
| `local-history/0.18.0` | [738b84b](patches/738b84b96cb51b3fafc5ef2667409ca189b90652.md) | 별도 보존 계보 |
| `main` | [90f9195](../patches/90f9195600dd54131c80a817bebdd88fd63fe52a.md) | 현재 기준의 조상 |
| `release/0.17.0` | [616599f](patches/616599f249500d3b437361959616298715a7712d.md) | 별도 보존 계보 |
| `release/0.17.1` | [953bbd9](patches/953bbd9999d0a01001c50916b074c28c836a1360.md) | 별도 보존 계보 |
| `release/0.17.2` | [a3bc428](patches/a3bc4285f3ade2aa8bebf88e6ad6f3b8f2e70f62.md) | 별도 보존 계보 |
| `release/0.17.3` | [822c215](patches/822c2156f56fd7edc485c5df956aa93a9faf5d74.md) | 별도 보존 계보 |
| `release/0.17.4` | [ce60a7a](patches/ce60a7a897c0af15e445025f1eb05f1584129653.md) | 별도 보존 계보 |
| `release/0.17.5` | [3725fe2](patches/3725fe26fb24de31e3a4f6b82e3366c35d29e8e0.md) | 별도 보존 계보 |
| `release/0.17.6` | [3541524](patches/3541524341756e1b173223cbf49135931e3ff384.md) | 별도 보존 계보 |
| `release/0.18.0` | [77d96eb](patches/77d96ebc870b64227cccbae72c9c92aa245b544d.md) | 별도 보존 계보 |
| `release/0.18.1` | [bce939d](patches/bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a.md) | 별도 보존 계보 |
| `release/0.18.2` | [10a3794](../patches/10a379463f5bfa8af845420d3c3936b4b211596d.md) | 현재 기준의 조상 |
| `release/unified-figma-0220` | [f64d9a9](../patches/f64d9a9e592343a0910cec236d358cd841b8e207.md) | 현재 기준의 조상 |

## 추가 커밋39개

| 커밋 | 실제 변경 제목 | 부모 수 |
| --- | --- | --- |
| [f0e81fc](patches/f0e81fcca8e6bb3e44d90d1509a4830c189c3701.md) | Figma Flow 0.16.1 기준선 | 0 |
| [90b0c62](patches/90b0c62463058af1e099965ca979888b6984a2cd.md) | 시안 품질 관문과 시각 품질 지침 추가 | 1 |
| [88b22bf](patches/88b22bfd41929ff7d91c59c91a2420f371efc99d.md) | 검토 시안 레이어 어휘 확장과 Figma 쓰기 전 일괄 점검 | 1 |
| [c27761a](patches/c27761a821ed256efb54886b38ad669dbcef9055.md) | 예제 시안을 시각 품질 요구사항에 맞게 다시 작성 | 1 |
| [bdd428c](patches/bdd428c20d0ce90292a922b0a63445585e3be66f.md) | 감사에서 확인된 경로·선택·브리프·테스트 실행 결함 수정 | 1 |
| [2bb7018](patches/2bb7018cc4fba5c18fcc9c7fa4441c1422696e7e.md) | 그라디언트·팔레트 샘플을 쓰기 전에 검증하고 고아 버튼 변형 충돌 방지 | 1 |
| [7ebc5bd](patches/7ebc5bd42e4dbe6868125d81c5f7a4e2131167de.md) | 문서의 명령을 실제 CLI 동작과 일치시킴 | 1 |
| [51f8b0a](patches/51f8b0a93dc3baa3e000f4bb7d5d319a0a257006.md) | CLI·서버 입력 오류를 깔끔한 실패로 처리 | 1 |
| [41d6ff1](patches/41d6ff1aadc3b79723e54438a72bc76d6fe5f491.md) | 본제작 import: 같은 크기 글자 역할 처리, 호환 안 되는 속성은 컴파일에서 거부 | 1 |
| [d48a056](patches/d48a056526d0880c4b88ca437384880834cb3851.md) | 가져오기 대체 변수 이름과 겹치는 역할 토큰을 쓰기 전에 거부 | 1 |
| [6a22eb3](patches/6a22eb38f254180cd1980c8ecf667e6052882b18.md) | 검토 계획에 표시한 값과 Figma에 쓰는 값이 다르면 거부 | 1 |
| [39897f3](patches/39897f3db1c7e6b4dbc256594cbabe008174ca65.md) | design_review CLI가 check_project와 같은 기준(바인딩 폴더)으로 경로를 해석 | 1 |
| [beb3912](patches/beb3912f8c3cdcf7f5302f30709a57c1f54816de.md) | 검토 패키지 준비 시 레이아웃 문제를 한 번에 모두 보고 | 1 |
| [586a5bf](patches/586a5bfb7cfd36639477b363617114d6a1997767.md) | 읽기 전용 design_actions.py status 명령 추가 | 1 |
| [5a025a7](patches/5a025a722aa87cd7272b9c533e18ffaba1cd7cfd.md) | 오류 보고 개선: 미사용 색 역할을 한 번에 모두 표시, CLI 오류에 cause 분류 | 1 |
| [3c67841](patches/3c678410d08c77f99d5b724d1728c138e1795df4.md) | 라이브 미리보기: 이전 스냅샷을 /before/revision/N/로 분리 | 1 |
| [8d6a9cf](patches/8d6a9cf182ab1f9d2d6bf335afe38cf1fd600945.md) | 기초 디자인 검증이 타입 지정 COLOR 역할을 받아들임 | 1 |
| [a1e9a74](patches/a1e9a74a04672574324d24185cbfaddc5f5e041e.md) | 화면 버튼의 숫자·서체 역할은 메인 컴포넌트에도 같은 역할이 있어야 계획 통과 | 1 |
| [b9785fa](patches/b9785fa25eb3cb2f6f196bfc9ff1ffaeb072700c.md) | Figma Flow 0.17.0 | 1 |
| [af04c96](patches/af04c9684a090347d02c568815d35f521f83e2cb.md) | Merge release/0.17.0: Figma Flow 0.17.0 | 2 |
| [616599f](patches/616599f249500d3b437361959616298715a7712d.md) | 시각 품질 지침의 role·오류 메시지 설명을 실제 검증 동작과 일치시킴 | 1 |
| [a36559a](patches/a36559aa505bce009d8075ce40bf6822080bebdf.md) | Merge release/0.17.0: 지침 문구 정정 | 2 |
| [953bbd9](patches/953bbd9999d0a01001c50916b074c28c836a1360.md) | Figma Flow 0.17.1: 품질 관문이 버튼 fill·글자 대비를 검사 | 1 |
| [c57cc8a](patches/c57cc8aa0892c141cfde03c0c33cefa244bde2eb.md) | Merge release/0.17.1: Figma Flow 0.17.1 | 2 |
| [a3bc428](patches/a3bc4285f3ade2aa8bebf88e6ad6f3b8f2e70f62.md) | Add MIT license (0.17.2) | 1 |
| [d795abe](patches/d795abeebde36931e4c4b8aa640d3c75dbb31f7a.md) | Merge release/0.17.2 | 2 |
| [822c215](patches/822c2156f56fd7edc485c5df956aa93a9faf5d74.md) | Validate image fit and require per-campaign plugin IDs (0.17.3) | 1 |
| [14ed049](patches/14ed0493c7ac86f3ea27dbff191ce8a44fc7e451.md) | Merge release/0.17.3 | 2 |
| [ce60a7a](patches/ce60a7a897c0af15e445025f1eb05f1584129653.md) | Reject production-invalid graphs at review; keep UI text out of key art (0.17.4) | 1 |
| [532b0e3](patches/532b0e33711d76bf7bfdb36793f92cdda84ced3e.md) | Merge release/0.17.4 | 2 |
| [3725fe2](patches/3725fe26fb24de31e3a4f6b82e3366c35d29e8e0.md) | Let implementation extend the selected graph without redesigning it (0.17.5) | 1 |
| [2da1c1c](patches/2da1c1cf59ad0fcd89f01734378226ba9237f8c8.md) | Merge release/0.17.5 | 2 |
| [3541524](patches/3541524341756e1b173223cbf49135931e3ff384.md) | Normalize selection paths; clear default variant-set radius (0.17.6) | 1 |
| [b81736e](patches/b81736ee077734337d39c2b065ad935e698ea046.md) | Merge release/0.17.6 | 2 |
| [f33249f](patches/f33249fa960d8666dfda75be5b493de4846bb6a4.md) | Report selected Figma readback, evidence freshness and embedded image size (0.18.0) | 1 |
| [1c3acdf](patches/1c3acdffcaccb373eed12559d5caa83b3f4fc83f.md) | Merge release/0.18.0 | 2 |
| [77d96eb](patches/77d96ebc870b64227cccbae72c9c92aa245b544d.md) | Use a supplied design system as the screen authoring standard | 1 |
| [738b84b](patches/738b84b96cb51b3fafc5ef2667409ca189b90652.md) | Merge design system guidance for 0.18.0 | 2 |
| [bce939d](patches/bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a.md) | Prepare public release documentation and portable setup for 0.18.1 | 1 |

전부 상세 기록과 연결했다. 루트·merge·문서 변경을 제외하지 않았다. 두 계보의 동일 제품 상태는 중복 인수나 새로운 릴리스로 세지 않는다.

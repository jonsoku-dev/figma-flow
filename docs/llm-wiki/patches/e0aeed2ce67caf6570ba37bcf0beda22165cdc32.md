<!-- patch-knowledge
{"commit":"e0aeed2ce67caf6570ba37bcf0beda22165cdc32","diff_sha256":"d039607cf754c44a996694efeda73ce7d2b36f754674a2ad338f634535caa6ed","files":["docs/llm-wiki/catalog.json","docs/llm-wiki/patches/0145921ca4ed5d22187b9e259cb8d8224b4a7d86.md","docs/llm-wiki/patches/03c4c8b73bd2fa7be32d5e019cb69f61aba1ad67.md","docs/llm-wiki/patches/06a40a1b83fac2f94b540d24e081ee87779e79ae.md","docs/llm-wiki/patches/0ad26187e423973a3895b3ae63e6953c0189761b.md","docs/llm-wiki/patches/1e64ada88f76180ab72d6be01c79841d9714335e.md","docs/llm-wiki/patches/28128ac57e43e314aade368f3f8c919c0246d22c.md","docs/llm-wiki/patches/2ae6c2aed4c6c45e79d92b10e46b0d3cb10e48de.md","docs/llm-wiki/patches/2cf4ce74557f9a2e65b8bc817b92eb3486067554.md","docs/llm-wiki/patches/2e974fa58123ab1835b117a55451bf837597182f.md","docs/llm-wiki/patches/493ee6f561112181f82e90a45b58fa35482c7219.md","docs/llm-wiki/patches/5d92cd61d7e09a444c5045ddc26911829d92b060.md","docs/llm-wiki/patches/6459de5ca0711f10629945fe36a2b4a2063fbbae.md","docs/llm-wiki/patches/65bd407b96ebaf14d6a965f6aa83c20c451795ca.md","docs/llm-wiki/patches/674335b0a46d426723e32ab3cc98029b8b6e3744.md","docs/llm-wiki/patches/721627bcc9a6eca2e283f879026d942a93a05a20.md","docs/llm-wiki/patches/7b5ae4091641430d891e0c110c8efdb9a845a6ce.md","docs/llm-wiki/patches/7ba864310c66d6f972cb4b9e15cacc04c3761ccd.md","docs/llm-wiki/patches/841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988.md","docs/llm-wiki/patches/8b984daa4733739c1c5ce72ab30232504d3fe4a4.md","docs/llm-wiki/patches/904175b5b8ed48f6c2a3bd5f8c23ed0066dfb3c2.md","docs/llm-wiki/patches/939f1b997d8cff3bd6efca5c28a9c2a23cd41785.md","docs/llm-wiki/patches/b1c3824d810a143b6c7eb5e1f6951828e950dfee.md","docs/llm-wiki/patches/b7209c96bfa57c008c59f351d55ac7f2d781811a.md","docs/llm-wiki/patches/ba390f93a7da8d74a4cd5cd1993c8a9244c91467.md","docs/llm-wiki/patches/bbe11d2a80604207b8efaba5c521834acad779b3.md","docs/llm-wiki/patches/c43b4fc6c3958c233ca403769b4ef255bd6708e5.md","docs/llm-wiki/patches/c7a3cdef85ad0fdb7bade6a3fe5fa1e896864dd2.md","docs/llm-wiki/patches/c80def58a7b0a875961f13c9ae7307bbc910ff8e.md","docs/llm-wiki/patches/d2e1b384ffe60e403c111b542df688b5e238deac.md","docs/llm-wiki/patches/d8a540b84376f39997583204aa6801aece6e31f0.md","docs/llm-wiki/patches/d9e8840c2fb51e8722cb2f95a3a810eb2f6de743.md","docs/llm-wiki/patches/dafe4bde488c82bb41cbf4096e4f83833c017fff.md","docs/llm-wiki/patches/dca7dfcb4ec97ee52427a40050e815f53880d47e.md","docs/llm-wiki/patches/e8ada75f03b253aed9ab4d9528872575f7cc8051.md","docs/llm-wiki/patches/ee296599d76993f3a8481edddf08ca9643c9301b.md","docs/llm-wiki/patches/f8e3b4a327afa4f939c3355cf94a601814936342.md","docs/llm-wiki/patches/fbf83b3f9aa43801306d2678a8ed3bbfc6c9f904.md","docs/llm-wiki/patches/fcace533169f7f37116ec1048857e7010790390e.md","docs/llm-wiki/releases.md"],"parents":["841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988"],"subject":"docs: publish complete 0.27 patch knowledge","tree":"f8acf722831ff4cfcff01c516c9bc98f89a4269a","versions":[{"path":"plugin.json","version":"0.27.0"},{"path":".codex-plugin/plugin.json","version":"0.27.0"}]}
-->

# docs: publish complete 0.27 patch knowledge

## 문제와 계기

0.27.0 제품 변경은 [제품 커밋 기록](841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988.md)에 있었지만, 215개 canonical과 39개 legacy-only 커밋의 누락 기록을 본문까지 채우고 통합 대조표에 반영할 필요가 있었다. 이 커밋은 그 과거 패치 근거를 Wiki로 발행하는 문서 전용 변경이다. 당시 0.27.0 태그가 이 문서 커밋을 가리키며, 현재 0.27.1 작업은 별도 pre-release 상태다.
## 결과 동작

저장소 Wiki에는 215 canonical 및 39 legacy-only 기록이 보존되고, 이 커밋은 catalog와 release 대조표를 포함한 40개 Wiki 경로를 추가·보완한다. 0.27.0 제품 파일이나 실행 동작은 이 커밋에서 바뀌지 않는다. 문서상의 태그 포인터는 제품 인수나 설치 성공을 뜻하지 않는다.
## 변경 파일과 인터페이스

첫 부모 `841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988` 대비 변경은 `docs/llm-wiki/catalog.json`, 37개 patch 페이지 추가와 기존 `904175b5...md` 페이지 보완, `docs/llm-wiki/releases.md` 갱신으로 구성된다(총 40개 Wiki 경로). 공개 API, 플러그인 인터페이스, 제품 코드에는 변경이 없다. 각 patch 페이지는 전체 커밋 ID를 파일명으로 사용하며, catalog metadata는 Git 객체의 diff 해시·부모·경로를 연결한다.
## 설계 이유와 출처

기록 도구의 계약에 따라 짧은 사용자 변경 기록은 CHANGELOG, 버전·태그 관계는 releases 대조표, 실제 변경·근거·한계는 전체 커밋별 페이지로 분리한다. 범위는 commit `e0aeed2...`의 첫 부모 대비 Git diff와 당시 0.27.0 제품 검증 요약이다. 상세 제품 동작과 그 인수의 한계는 [0.27.0 제품 기록](841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988.md)에 둔다.
## 호환성·이관·복구

실행 코드, 설정 형식, 데이터, 설치 상태를 바꾸지 않으므로 제품 데이터 이관이나 복구 단계는 없다. 기록은 기존 전체 커밋 ID와 patch 경로를 유지하고 버전 태그·commit 대응을 명시한다. 문서의 0.27.0 태그 연결은 당시 Git 이력상의 위치일 뿐 현재 pre-release 설치를 입증하지 않는다.
## 검증과 미검증

당시 최종 local 검증 14개 명령은 모두 exit 0이었다. 보고된 결과는 root Python 1,107개 중 1,105 pass·2 skip, Node 299개 중 298 pass·1 skip, finalize 74, design 16, PostgreSQL backend 58, packaging 4, demo 2다. 제품 관찰 요약은 R8에서 44 screens·4,820 nodes·2 Groups·24 mains·2 component sets·494 instances·69 variables를 확인했고, 3,171개 geometry bbox 차이 0, 기존 550 clips와 314 reaction을 보존했다. 이 수치는 당시 제품 검증 기록의 범위이며 문서 커밋이 새로 실행한 검사 결과가 아니다. 원격 CI·배포·설치 후속은 당시 pending이었다.
## 한계와 후속 개선

Wiki의 구조 검사와 과거 local 결과는 당시 기록의 완전성이나 실제 제품 동작 전체를 보증하지 않는다. R8 수치는 해당 Figma 실행·관찰 범위에 한정되며, 설치 후 검증과 원격 결과는 pending으로 남았다. 후속 0.27.1 작업 및 그 현재 인수 상태는 이 문서 커밋의 성공으로 소급해 해석하지 않는다.
## 관련 기록

- [0.27.0 제품 구현 및 검증](841aa58a7f0f5fabe68aaaa7bdee1cd3ba64c988.md)
- [버전·태그 대조표](../releases.md#v0.27.0)
- [Wiki 기록 계약](../README.md)

원문 대조: `git show e0aeed2ce67caf6570ba37bcf0beda22165cdc32`.

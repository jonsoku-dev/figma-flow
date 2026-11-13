# Figma Design 그래프 검토

기획자·디자이너·개발자는 같은 Design 페이지에서 선택한 요구사항, 화면, 컴포넌트와 인수 근거를 검토한다. 제품 graph가 정본이며 검토 보드의 카드와 관계는 선택한 노드 ID와 원본 SHA를 보존한다.

1. [기능 그래프](graph.json)에서 필요한 노드 ID를 고른다. 관계 양끝을 모두 선택해야 보드에 나타난다.
2. 대상 파일과 페이지를 고정해 새 계획을 생성한다.
3. 등록한 Design 작업공간의 `native-edit` 작업에서 적용하고 실제 보드·연결·재실행 결과를 확인한다.

```sh
python3 tools/native_edit.py graph-review --graph specs/graph-review/graph.json \
  --node REQ-plan --node SCR-plan --node AC-plan --node TEST-design \
  --file-key FILE_KEY --page-id PAGE_ID --out reviewed-plan.json
```

기획자는 인수 조건에 누락된 근거를 확인한다. 디자이너는 같은 입력의 재실행에서 프레임과 main·instance를 대조한다. 개발자는 선언된 API와 실제 getter 영수증을 대조한다. 각 항목의 소스와 검증 근거는 [인수 그래프](graph.json)에서 추적한다.

[0.31 실제 반응형 검증](../../docs/responsive-web-verification.md) · [API 우선순위와 관측](../../docs/api-priority.md) · [이전 릴리스 원문](https://github.com/jonsoku-dev/figma-flow/blob/v0.31.0/specs/graph-review/spec.md)

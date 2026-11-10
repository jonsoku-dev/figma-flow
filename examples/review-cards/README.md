# 복습 카드 감사 실습
실제 복습 카드의 로컬 사본이다. 코드 노드와 가져온 파일, 검사 노드와 실행한 테스트를 그래프에 선언했다. 함께 제공한 증거는 Node 테스트 실행 결과다.
플러그인 루트에서 다음 명령으로 코드 의존성과 기획을 검사하고 디자인을 생성한다.

```sh
python3 tools/audit_project.py --project examples/review-cards --graph graph.json --bindings bindings.json --brief brief.md --spec specs/retry.md --out /tmp/cards-audit-new
python3 tools/design_bundle.py --graph examples/review-cards/graph.json --design examples/review-cards/design.json --out /tmp/cards-design-new
```

감사는 패턴 밖의 자연어가 있으면 종료 2로 검토 대상을 남긴다. 복사본에서 CODE-CARDS-RETRY → CODE-CARDS-APP의 depends-on 관계를 삭제하고 brief.md에 “정답을 본 상태에서 ‘다시 연습’을 선택하면 항상 같은 카드의 질문을 다시 보여 준다.”를 추가해 다시 검사하면 누락·모순을 볼 수 있다. 기준 프로젝트를 고쳐 쓰지 말고 복사본에서 실습한다.

# Synthetic web carousel fixture

This fixture is generated data for the `web-carousel` compiler. Its screenshots are 1 by 1 pixel placeholders, and its screen geometry and observations are illustrative. It does not represent a real SaaS page or prove browser behavior.

Copy this directory before running the commands because the compiler writes a new graph and plan next to the inputs:

```sh
work_dir="$(mktemp -d)"
cp -R tests/fixtures/web_carousel_synthetic/. "$work_dir/"
python3 -B tools/native_edit.py web-carousel \
  --graph "$work_dir/screens.json" \
  --observations "$work_dir/observations.json" \
  --out "$work_dir/carousel-graph.json"
python3 -B tools/native_edit.py web-design \
  --graph "$work_dir/carousel-graph.json" \
  --file-key demo \
  --page-id 1:1 \
  --out "$work_dir/plan.json"
```

The first command prints a `compiled-not-applied` receipt. The second prints a `prepared-not-executed` receipt. Neither command edits Figma.

# Replay optional native evidence tests

Use `tools/replay_optional_tests.py` to run the native readback check against operator supplied evidence and the private Shadow Troupe and Moss Choir regression fixtures. Pass the exact manifest, readback, renderer packet, generated plugin code, renderer source directory, and fixture roots. The command writes a JSON receipt with input hashes, the named test results, and the tampering checks. The receipt omits file paths and Figma identifiers.

The command creates an isolated temporary test checkout. It copies the three test files and links the `tools` and `figma-bridge` source directories. It links only the fixture roots you pass, then reads the original fixture files through those links. The command removes the temporary checkout after each run. It does not copy or write through the original fixtures.

For the native readback replay, the command copies the manifest and creates `renderer-snapshot.json` beside that copy. The snapshot records local source paths and hashes so `verify_native_review` can reconstruct the renderer that created the packet. The command does not write beside the original manifest.

## Run the replay

Pass each input path from the local evidence you want to verify. The readback path must match the path pinned in the manifest. Choose a new receipt path for each run.

```sh
python3 tools/replay_optional_tests.py \
  --shadow-root "$SHADOW_TROUPE_ROOT" \
  --moss-root "$MOSS_CHOIR_ROOT" \
  --manifest "$EVIDENCE_ROOT/review/directions.json" \
  --readback "$READBACK_PATH" \
  --packet "$PACKET_PATH" \
  --code "$PLUGIN_CODE_PATH" \
  --source-dir "$RENDERER_SOURCE_DIR" \
  --receipt "$EVIDENCE_ROOT/optional-readback-replay.json"
```

`$SHADOW_TROUPE_ROOT` and `$MOSS_CHOIR_ROOT` must each contain the original `native-layout.json`. `$RENDERER_SOURCE_DIR` must contain `semantic_tokens.js`, `native_annotations.js`, `native_semantic_read.js`, `foundation_palette.js`, `design_note_board.js`, and `direction_review.js`. The packet and plugin code must come from the same native review task. The verifier compares their hashes and regenerated code before it accepts the readback.

The receipt records the exact test IDs and pass, skip, or failure counts for all three cases. It counts a case as passed only when every test ran and none skipped. A pass for `tests.test_figma_draft.OptionalLiveReadbackTests.test_supplied_native_evidence_and_tampering` means the native readback matched its original packet and both reaction destination and design link tampering were rejected. The check verifies consistency with supplied evidence. It does not authenticate who produced that evidence.

## CI skips

Clean CI has no operator readback or renderer packet, so it skips the opt-in test with `Optional operator evidence not supplied`. CI also skips `test_shadow_troupe_light_bars_are_placeholder_bars` when the private `shadow-troupe/native-layout.json` fixture is absent. The separate Node test `actual saved initial Moss tint packet is rejected without writes` skips when the private Moss Choir fixture is absent. Those skips preserve missing evidence as missing. Provide the original inputs to replay each check locally.

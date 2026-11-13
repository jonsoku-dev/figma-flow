# Pinned Figma REST API inventory

This offline catalog covers all 59 operations in Figma's official
[`rest-api-spec`](https://github.com/figma/rest-api-spec/tree/af027cd20aca8326a41115e4d15bbdf875158e81),
OpenAPI version 0.47.0. The upstream specification is beta. Declaration presence
does not prove runtime behavior, account access, or Figma Flow implementation.

`source.json` pins the commit, original YAML SHA-256, compressed source and MIT
license hashes. `openapi.yaml.gz` preserves the exact upstream YAML with a zero
gzip timestamp. `LICENSE` is the unmodified upstream MIT license. `index.json`
is generated from that source and includes methods, paths, operation IDs,
concrete path/query/header parameter schemas, resolved request body schemas,
security alternatives, OAuth scopes, declared account restrictions, and links.
Rate limit tiers are `null` because this source declares none; access notes
are extracted from descriptions, which remain included in full.

Run from the repository root:

```sh
python3 tools/figma_rest_inventory.py search variables --method GET --limit 0
python3 tools/figma_rest_inventory.py search getFileNodes
python3 tools/figma_rest_inventory.py template getFileNodes
python3 tools/figma_rest_inventory.py template postComment
python3 tools/figma_rest_inventory.py curl getFileNodes --path file_key=YOUR_FILE_KEY --query ids=1:2,3:4
python3 tools/figma_rest_inventory.py curl postComment --path file_key=YOUR_FILE_KEY --body-file reviewed-comment.json --auth oauth
```

Search and templates require only Python's standard library, work offline, and
never read credentials or send HTTP requests. Templates are JSON drafts with
named placeholders for every required parameter and illustrative request bodies.
Required body properties are included; when none are required, declared optional
properties are shown. Union schemas illustrate the first alternative. Review
the included schema before use: generated values are examples, not validated or
authorized requests. Authentication alternatives and scope declarations are
metadata; no credential headers are generated.

`curl` exports a copyable `shell_command` without executing it. Supply concrete
required path/query arguments, and a reviewed local JSON file for required
bodies. Optional query parameters may also be supplied. Parameter names must
exist in the pinned operation; values are URL encoded. Body files are checked
for valid JSON syntax; schema and business validation belong to the caller and
Figma. The command uses the
declared method and a `FIGMA_TOKEN` environment reference for either
`X-Figma-Token` (default) or OAuth Bearer authentication. Set that variable
privately in your shell before running the reviewed command. Account access,
scopes and action authorization must still be satisfied. The command disables
curl configuration files, URL globbing and redirects, and restricts protocols
to HTTPS. Nothing evaluates or runs the returned command automatically.

Regeneration requires the pinned parser, with no network needed once installed:

```sh
python3 -m pip install -r library/figma-rest/requirements.txt
python3 tools/figma_rest_inventory.py generate
python3 tools/figma_rest_inventory.py verify
python3 -m unittest discover -s tests -p test_figma_rest_inventory.py
```

`verify` checks source/license hashes and byte-identical index regeneration.
Changing the source pin is an explicit maintenance action; these commands never
download or update it.

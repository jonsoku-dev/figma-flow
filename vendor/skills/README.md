# Pinned design skill sources

Figma Flow packages these upstream files as explicit dependencies. `manifest.json` records each repository, commit, original subtree, license files and SHA-256 for every packaged file. Original skill files are copied without modification; repository license and notice files are placed beside them. These third-party files retain their own licenses, independently of Figma Flow's MIT license.

| ID | Source pin | License |
| --- | --- | --- |
| `impeccable` | [Impeccable 4.0.2](https://github.com/pbakaus/impeccable/tree/fc2e694afca1ac0cc384b4fe56bab3335fea7912/.agents/skills/impeccable) | [Apache-2.0](impeccable/LICENSE) and [upstream notices](impeccable/NOTICE.md) |
| `design-taste-frontend` | [Taste Skill](https://github.com/Leonxlnx/taste-skill/tree/3c7017d636c3a4aad378433ea6d0cfa6c921da4a/skills/taste-skill) | [MIT](design-taste-frontend/LICENSE) |
| `unslop` | [Damir Sokolovsky's Unslop](https://github.com/heydamir/unslop/tree/97daa3eb365670ea3f87ed85356cbfcee18105a5/skills/unslop) | [CC BY 4.0](unslop/LICENSE), with [author attribution](unslop/CITATION.cff) |

The complete skill subtrees are retained, including relative references, scripts, agent definitions and image references. Bundling a file does not enable its hooks, install tools, grant access, or authorize execution. Figma Flow's own workflow and the current user's instructions govern which guidance and tools apply.

The [Figma Flow Unslop adaptation](../../skills/figma-flow/references/unslop.md) is a separate, changed document. The original Unslop package here is source material, not a claim that its snapshot or story tools ran. Impeccable uses the pristine official release; unrelated customizations from a developer's global skill directory are not included. The music/video skill whose exact ID is `taste` is not a dependency.

At first use, validate this bundle with `python3 tools/skill_dependencies.py --check` from the plugin root. Validation reads the packaged files and does not download newer versions or modify the installation. Read only the references needed for the requested task. Personal setup files and writable caches stay outside this directory.

To update a dependency, choose an explicit upstream commit, review its changes and redistribution terms, copy its complete skill subtree and listed repository-level files, then regenerate that dependency's file hashes in `manifest.json`. Run the dependency, review and routing tests before changing the plugin version. Keep the source, license and application-scope changes visible in the release notes; do not rewrite old review evidence to make it match a new source.

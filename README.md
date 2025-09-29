# Open-CWM Module 1: Executable Repository Images

This repository contains the pilot implementation of the Open-CWM Module 1
pipeline. The goal of Module 1 is to produce reproducible, executable
repository images for permissively licensed Python projects.

## Repository Layout

```
repo_catalog/                # Source repositories and metadata
orchestrator/                # Python package for the control plane
  run.py                     # CLI entrypoint
  pipeline.py                # Stage machine + orchestration logic
  catalog.py                 # Repo catalog loader
  models.py                  # Dataclasses shared across stages
  utils.py                   # Utility helpers (subprocess, filesystem)
builders/                    # (future) build strategy implementations
runners/                     # (future) test runners and collectors
schemas/                     # JSON Schema contracts for emitted artifacts
artifacts/                   # Local cache for manifests, logs, and images
ci/                          # Development automation stubs
```

## Quickstart

1. **List available repositories**

   ```bash
   python -m orchestrator.run list
   ```

2. **Plan a repository build**

   ```bash
   python -m orchestrator.run plan --repo-id pallets_flask
   ```

   The CLI will automatically execute the discovery stage (cloning the
   repository if necessary) and produce a plan summary stored under
   `.open-cwm/state/<repo>/plan.json`.

3. **Run additional stages**

   ```bash
   python -m orchestrator.run build --repo-id pallets_flask
   python -m orchestrator.run test --repo-id pallets_flask
   python -m orchestrator.run package --repo-id pallets_flask
   python -m orchestrator.run publish --repo-id pallets_flask
   ```

   Stage outputs and normalized artifacts (manifest, environment manifest,
   coverage placeholder, etc.) are written under `.open-cwm/` by default.

4. **Inspect pipeline status**

   ```bash
   python -m orchestrator.run status --repo-id pallets_flask
   ```

## Schemas

Machine-readable JSON Schemas describing Module 1 artifacts live in the
[`schemas/`](schemas) directory:

- `repo_image_manifest.schema.json`
- `test_index.schema.json`
- `env_manifest.schema.json`

The orchestrator emits placeholder files conforming to these contracts so
that downstream modules have predictable interfaces during the pilot phase.

## Development Notes

- The orchestrator uses Git to clone repositories during the discovery stage.
  If a repository has already been cloned under `.open-cwm/repos/<repo_id>` the
  clone step is skipped.
- The plan stage infers a build strategy based on the presence of CI workflows
  and common Python packaging files. Build/test/package stages currently
  emit structured placeholders that will be replaced with full implementations
  as the project matures.
- The repository includes stub directories (`builders/`, `runners/`) ready for
  future modules and strategies.

## Make Targets (CI Stubs)

The `ci/` directory contains a thin Makefile and pipeline placeholder to ease
future integration with continuous integration systems.

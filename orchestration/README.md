# Executable Orchestration Vertical Slice

This package compiles and executes the provider-neutral `automate` workflow
against a deterministic mock role executor.

It intentionally does not contain model SDKs, external integrations, real test
execution, Wiki writes, ticket writes, or deployment behavior.

## Commands

```text
python -m orchestration validate
python -m orchestration compile
python -m orchestration --db runtime.db start --work-item "Example work item"
python -m orchestration --db runtime.db inspect <run-id>
python -m orchestration --db runtime.db approve <run-id> --by <person> --reason <reason>
python -m orchestration --db runtime.db reject <run-id> --by <person> --reason <reason>
python -m orchestration --db runtime.db resume <run-id>
```

Gate decisions and resumes are separate commands so approval never implicitly
executes downstream work. SQLite holds runtime metadata and an append-only event
ledger. Artifact payloads are canonical JSON in SQLite for this slice; the
schema leaves room for future file-backed large artifacts.

## Demonstration

```text
python tools/demo_automate.py --db demo.db
```

The demonstration rejects and reworks both the design and release gates before
reaching `COMPLETED`.

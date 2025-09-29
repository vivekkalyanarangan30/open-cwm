.PHONY: plan build test package publish status list

REPO ?= pallets_flask
CATALOG ?= repo_catalog/repos.yaml
WORKSPACE ?= .open-cwm

list:
	python -m orchestrator.run list --catalog $(CATALOG)

status:
	python -m orchestrator.run status --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

plan:
	python -m orchestrator.run plan --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

build:
	python -m orchestrator.run build --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

test:
	python -m orchestrator.run test --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

package:
	python -m orchestrator.run package --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

publish:
	python -m orchestrator.run publish --catalog $(CATALOG) --workspace $(WORKSPACE) --repo-id $(REPO)

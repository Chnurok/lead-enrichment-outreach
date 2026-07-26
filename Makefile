PYTHON ?= python3
DEMO_OFFER ?= AI-assisted lead enrichment and outreach
DEMO_TMP_DIR ?= .tmp

.PHONY: test verify extension-check extension-backend-smoke demo-ui-smoke demo demo-quick demo-story demo-artifacts demo-ready demo-review-required demo-blocked demo-refusal demo-ui demo-launch demo-launch-public demo-health demo-public-health demo-smoke-local ui workflow-demo batch-demo ready-export-demo

test:
	$(PYTHON) -m unittest discover -s tests -q

extension-check:
	node --check extension/background.js
	node --check extension/options.js
	node --check extension/popup.js
	node --check extension/content.js
	node extension/smoke-test.js
	node extension/popup-smoke-test.js

extension-backend-smoke:
	$(PYTHON) scripts/smoke_extension_backend.py

demo-ui-smoke:
	$(PYTHON) scripts/smoke_demo_ui.py

verify: test extension-check extension-backend-smoke demo demo-ui-smoke batch-demo ready-export-demo

demo-quick:
	@echo "Lead Enrichment Outreach demo"
	@echo
	@echo "1) Proof in 20 seconds"
	@echo "   make demo"
	@echo
	@echo "2) Operator UI"
	@echo "   make demo-ui"
	@echo "   open http://127.0.0.1:8095"
	@echo
	@echo "3) Batch handoff"
	@echo "   make batch-demo"
	@echo "   make ready-export-demo"
	@echo
	@echo "Docs: README.md and docs/demo/README.md"
	@echo
	@echo "Ship checks"
	@echo "   make verify"

demo-story:
	@echo "Demo story :: company/domain -> dossier -> trust gate -> draft -> human decision"
	@echo
	@echo "Show in this order:"
	@echo "  1. ready path: product works end-to-end"
	@echo "  2. review_required: draft is gated until human review"
	@echo "  3. blocked: workflow stops before outreach"
	@echo "  4. UI: operator can inspect, edit, approve, export"
	@echo "  5. batch export: only ready leads reach ops"

demo-artifacts:
	@echo "Demo artifacts"
	@echo "  ready            :: examples/demo/ready/deepl-dossier.json"
	@echo "  ready draft      :: examples/demo/ready/deepl-draft.json"
	@echo "  review_required  :: examples/demo/review_required/mistral-ai-dossier.json"
	@echo "  blocked          :: examples/demo/blocked/unknown-co-dossier.json"
	@echo "  refusal          :: examples/demo/refusal/review-required-draft-refusal.json"
	@echo "  batch input      :: examples/demo-leads.csv"
	@echo "  batch output     :: examples/demo-output.json"
	@echo "  ui review file   :: examples/demo-review.json"

ui:
	$(PYTHON) ui/review_server.py --review-file examples/demo-review.json --host 127.0.0.1 --port 8095

demo-ui:
	$(PYTHON) ui/review_server.py --demo --review-file examples/demo-review.json --demo-batch-file examples/demo-output.json --host 127.0.0.1 --port 8095

demo-launch:
	$(PYTHON) ui/review_server.py --demo --review-file examples/demo-review.json --demo-batch-file examples/demo-output.json --host 127.0.0.1 --port 8095

demo-launch-public:
	$(PYTHON) ui/review_server.py --demo --public --review-file examples/demo-review.json --demo-batch-file examples/demo-output.json --port 8095

demo-health:
	curl -fsS http://127.0.0.1:8095/healthz

demo-public-health:
	TOKEN=$$(sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' /etc/lead-enrichment-demo.env 2>/dev/null); \
	curl -fsS -H "X-Review-Token: $$TOKEN" http://127.0.0.1:8095/healthz

demo-smoke-local:
	./deploy/smoke-demo.sh http://127.0.0.1:18095

demo-ready:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/ready/deepl-dossier.json').read_text()); print('ready ::', artifact['company']); print('status ::', artifact['review']['status']); print('best_contact ::', artifact['best_contact_email']); print('next_step ::', artifact['review']['next_step'])"
	@echo
	@echo "Draft preview: examples/demo/ready/deepl-draft.json"

demo-review-required:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/review_required/mistral-ai-dossier.json').read_text()); print('review_required ::', artifact['company']); print('status ::', artifact['review']['status']); print('best_contact ::', artifact['best_contact_email']); print('warnings ::', '; '.join(artifact['warnings'])); print('next_step ::', artifact['review']['next_step'])"

demo-blocked:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/blocked/unknown-co-dossier.json').read_text()); print('blocked ::', artifact['company']); print('status ::', artifact['review']['status']); print('warnings ::', '; '.join(artifact['warnings'])); print('next_step ::', artifact['review']['next_step'])"

demo-refusal:
	@mkdir -p "$(DEMO_TMP_DIR)"; \
	out_file="$(DEMO_TMP_DIR)/leo-demo-refusal.out"; \
	err_file="$(DEMO_TMP_DIR)/leo-demo-refusal.err"; \
	$(PYTHON) skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json --offer "$(DEMO_OFFER)" >"$$out_file" 2>"$$err_file"; status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "Expected refusal, but draft generation succeeded"; \
		cat "$$out_file"; \
		exit 1; \
	fi; \
	echo "refusal :: exit $$status"; \
	cat "$$err_file"

workflow-demo:
	@$(PYTHON) skill/scripts/workflow.py --dossier-json examples/demo/ready/deepl-dossier.json --offer "$(DEMO_OFFER)"

batch-demo:
	@$(PYTHON) ui/review_server.py --build-demo-batch-only --demo-batch-file examples/demo-output.json --demo-offer "$(DEMO_OFFER)"

ready-export-demo:
	@$(PYTHON) skill/scripts/export_ready_leads.py examples/demo-output.json

demo: demo-ready demo-review-required demo-blocked demo-refusal

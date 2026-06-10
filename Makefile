PYTHON ?= python3
DEMO_OFFER ?= AI-assisted lead enrichment and outreach

.PHONY: test demo demo-ready demo-review-required demo-blocked demo-refusal demo-ui ui workflow-demo

test:
	$(PYTHON) -m unittest discover -s tests -q

ui:
	$(PYTHON) ui/review_server.py --review-file examples/demo-review.json --host 127.0.0.1 --port 8095

demo-ui:
	$(PYTHON) ui/review_server.py --seed-demo --review-file examples/demo-review.json --host 127.0.0.1 --port 8095

demo-ready:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/ready/deepl-dossier.json').read_text()); print('ready ::', artifact['company']); print('status ::', artifact['review']['status']); print('best_contact ::', artifact['best_contact_email']); print('next_step ::', artifact['review']['next_step'])"
	@echo
	@echo "Draft preview: examples/demo/ready/deepl-draft.json"

demo-review-required:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/review_required/mistral-ai-dossier.json').read_text()); print('review_required ::', artifact['company']); print('status ::', artifact['review']['status']); print('best_contact ::', artifact['best_contact_email']); print('warnings ::', '; '.join(artifact['warnings'])); print('next_step ::', artifact['review']['next_step'])"

demo-blocked:
	@$(PYTHON) -c "import json, pathlib; artifact = json.loads(pathlib.Path('examples/demo/blocked/unknown-co-dossier.json').read_text()); print('blocked ::', artifact['company']); print('status ::', artifact['review']['status']); print('warnings ::', '; '.join(artifact['warnings'])); print('next_step ::', artifact['review']['next_step'])"

demo-refusal:
	@$(PYTHON) skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json --offer "$(DEMO_OFFER)" >/tmp/leo-demo-refusal.out 2>/tmp/leo-demo-refusal.err; status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "Expected refusal, but draft generation succeeded"; \
		cat /tmp/leo-demo-refusal.out; \
		exit 1; \
	fi; \
	echo "refusal :: exit $$status"; \
	cat /tmp/leo-demo-refusal.err

workflow-demo:
	@$(PYTHON) skill/scripts/workflow.py --dossier-json examples/demo/ready/deepl-dossier.json --offer "$(DEMO_OFFER)"

demo: demo-ready demo-review-required demo-blocked demo-refusal

.PHONY: install lint test eval corpus api console up down

install:   ## Install dev dependencies
	pip install -r requirements-dev.txt
corpus:    ## Regenerate the synthetic document set and golden questions
	python -m ragp.corpus.generator
lint:
	ruff check .
test:
	pytest -q
eval:      ## Golden-set evaluation with quality gate
	python -m ragp.eval.run --gate
api:
	uvicorn ragp.api:app --reload
console:
	streamlit run streamlit_app.py
up:        ## PostgreSQL + API + console
	cp -n .env.example .env || true; docker compose up --build -d
down:
	docker compose down

# Contributing

1. `pip install -r requirements-dev.txt`
2. To add knowledge, edit `ragp/corpus/spec.py` and run `make corpus` — documents and golden questions are regenerated together.
3. `make lint test eval` must pass. Never lower a gate threshold to make a change pass; explain metric changes in the PR.
4. Access-control and stale-version regressions block a merge.

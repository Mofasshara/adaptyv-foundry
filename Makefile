.PHONY: test eval

test:
	. .venv/bin/activate && python3 -m pytest -q

eval:
	. .venv/bin/activate && python3 -m evals.run_eval

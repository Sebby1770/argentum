.PHONY: test install cli studio
install:
	python3 -m pip install -e ".[dev]"
test:
	PYTHONPATH=src python3 -m pytest -q
cli:
	PYTHONPATH=src python3 -m argentum vanilla --spot 100 --strike 100 --rate 0.05 --vol 0.2 --texp 1
studio:
	PYTHONPATH=src python3 -m argentum studio --port 8787

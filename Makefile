.PHONY: generate dry-run setup

setup:
	python3 -m pip install -r requirements.txt

generate:
	python3 scripts/generate_readme.py > README.md

dry-run:
	python3 scripts/generate_readme.py | sed -n '1,80p'

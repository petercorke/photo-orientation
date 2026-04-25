.FORCE:

BLUE=\033[0;34m
BLACK=\033[0;30m

help:
	@echo "$(BLUE) make install      - install package in editable mode"
	@echo " make install-auto - install package with auto extras"
	@echo " make build        - build package"
	@echo " make dist         - build dist files"
	@echo " make upload       - upload dist files to PyPI"
	@echo " make clean        - remove build artifacts"
	@echo " make help         - this message$(BLACK)"

install:
	pip install -e .

install-auto:
	pip install -e .[auto]

build: .FORCE
	python -m build

dist: .FORCE
	python -m build

upload: .FORCE
	twine upload dist/*

clean: .FORCE
	-rm -rf build dist *.egg-info

SPHINX_APIDOC_OPTIONS=members,show-inheritance poetry run sphinx-apidoc -o docs/source src
poetry run sphinx-build -M html docs docs/_build

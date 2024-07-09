#!/bin/bash -e

# Install the local copy of the package from the files in ./
python3 -m venv env
. env/bin/activate
pip3 install --editable .

#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "$0")

sudo apt-get update
sudo apt-get install -y wget tar coreutils
pip install --upgrade pip
pip install -r ${SCRIPT_DIR}/requirements.txt
git config --global user.email "mark.luko@gmail.com"
git config --global user.name "Mark Luko"

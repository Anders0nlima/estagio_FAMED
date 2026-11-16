#!/usr/bin/env bash
# Script de build automático para deploy no Render.com
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py setup_admin

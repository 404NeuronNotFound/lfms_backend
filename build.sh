#!/usr/bin/env bash
set -o errexit

echo "==> Python: $(python --version)"
echo "==> Pip: $(pip --version)"

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed --force
#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install Django==4.2.16
pip install djangorestframework==3.14.0
pip install djangorestframework-simplejwt==5.3.1
pip install django-cors-headers==4.3.1
pip install Pillow==10.4.0
pip install python-dotenv==1.0.1
pip install gunicorn==21.2.0
pip install whitenoise==6.6.0
pip install dj-database-url==2.1.0
pip install psycopg2-binary==2.9.9

python manage.py collectstatic --no-input
python manage.py migrate
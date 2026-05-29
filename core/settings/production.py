from .base import *

DEBUG = False

ALLOWED_HOSTS = []  # será preenchido com o domínio real no futuro

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': '',      # será preenchido no futuro
        'USER': '',      # será preenchido no futuro
        'PASSWORD': '',  # será preenchido no futuro
        'HOST': '',      # será preenchido no futuro
        'PORT': '5432',
    }
}

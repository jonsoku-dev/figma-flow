"""Secure-by-default service settings; secrets and data are owned by the operator."""
import os
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent
ENVIRONMENT = os.environ.get('LH_ENV', 'production')
if ENVIRONMENT not in {'production', 'staging', 'development'}:
    raise ValueError('LH_ENV must be production, staging, or development')
PRODUCTION = ENVIRONMENT == 'production'
SECRET_KEY = os.environ.get('LH_SECRET_KEY', '')
if len(SECRET_KEY) < 50:
    raise ValueError('Set LH_SECRET_KEY to an operator-owned random secret of at least 50 characters')
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('LH_ALLOWED_HOSTS', '').split(',') if host.strip()]
if not ALLOWED_HOSTS or any('*' in host or host.startswith('.') for host in ALLOWED_HOSTS):
    raise ValueError('Set exact LH_ALLOWED_HOSTS; wildcard hosts are not permitted')
SITE_URL = os.environ.get('LH_SITE_URL', '')
site = urlsplit(SITE_URL)
if site.scheme not in ({'https'} if PRODUCTION else {'http', 'https'}) or not site.hostname or site.username or site.password or site.query or site.fragment or site.path not in {'', '/'}:
    raise ValueError('Set LH_SITE_URL to the exact service origin; production requires HTTPS')
site_host = '[' + site.hostname + ']' if ':' in site.hostname else site.hostname
if site_host.lower() not in {host.lower() for host in ALLOWED_HOSTS}:
    raise ValueError('LH_SITE_URL host must be one of the exact LH_ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = [SITE_URL.rstrip('/')]

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'django.contrib.humanize', 'django.contrib.postgres', 'axes', 'booking.apps.BookingConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'config.middleware.ResponsePolicyMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware', 'axes.middleware.AxesMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates',
    'DIRS':[BASE_DIR / 'templates'], 'APP_DIRS':True,
    'OPTIONS':{'context_processors':[
        'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages', 'config.context.service_context',
    ]}}]

DATABASES = {'default':{
    'ENGINE':'django.db.backends.postgresql',
    'NAME':os.environ.get('LH_DB_NAME', 'littlehands'), 'USER':os.environ.get('LH_DB_USER', 'littlehands_runtime'),
    'PASSWORD':os.environ.get('LH_DB_PASSWORD', ''), 'HOST':os.environ.get('LH_DB_HOST', '127.0.0.1'),
    'PORT':os.environ.get('LH_DB_PORT', '55439'), 'CONN_MAX_AGE':60, 'CONN_HEALTH_CHECKS':True,
    'OPTIONS':{'connect_timeout':5},
}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'django.contrib.auth.backends.ModelBackend']
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher']
AUTH_PASSWORD_VALIDATORS = [
    {'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},
    {'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25
AXES_LOCKOUT_PARAMETERS = [['ip_address', 'username']]
AXES_RESET_ON_SUCCESS = True
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'session_list'
LOGOUT_REDIRECT_URL = 'session_list'
SESSION_COOKIE_NAME = '__Host-littlehands' if PRODUCTION else 'littlehands_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 1800
CSRF_COOKIE_NAME = '__Host-littlehands-csrf' if PRODUCTION else 'littlehands_csrf'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = PRODUCTION
if os.environ.get('LH_TRUST_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION
SECURE_HSTS_PRELOAD = PRODUCTION
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = Path(os.environ.get('LH_STATIC_ROOT', str(BASE_DIR / 'staticfiles')))
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
LOGGING = {'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'}},
    'root':{'handlers':['console'],'level':'WARNING'}}

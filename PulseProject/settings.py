from pathlib import Path
import os
import json
from dotenv import load_dotenv

# load environment variables
load_dotenv()

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# You could use this to display warnings in templates
# or modify behavior slightly between environments
IS_DEVELOPMENT = ENVIRONMENT == 'development'


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'


SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False') == 'True'
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False') == 'True'
CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'False') == 'True'


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

ALLOWED_HOSTS = [
    'pulse-deploy-production.up.railway.app',
    'https://pulse-deploy-production.up.railway.app',
    'pulse-production-3383.up.railway.app',
    '0673-2601-282-227e-a550-d550-622a-bcab-8663.ngrok-free.app',
    '57d0-2601-282-227f-5690-ec91-59b2-7b21-980d.ngrok-free.app',
    '05dd-2607-fb91-11af-8951-c2b-b888-dca-91fb.ngrok-free.app',  # New ngrok URL
    'localhost',
    '127.0.0.1',
    # Wildcard for ngrok domains
    '*.ngrok-free.app',
    '*.railway.app',  # Add this for all Railway subdomains
]

CSRF_TRUSTED_ORIGINS = [
    'https://pulse-deploy-production.up.railway.app',
    'https://pulse-production-3383.up.railway.app',  # Add this
    'http://localhost:8000',
    'https://localhost:8000',
    'http://127.0.0.1:8000',
    'https://127.0.0.1:8000',
    # Wildcard for ngrok domains
    'https://*.ngrok-free.app',
    'https://0673-2601-282-227e-a550-d550-622a-bcab-8663.ngrok-free.app',
    'https://57d0-2601-282-227f-5690-ec91-59b2-7b21-980d.ngrok-free.app',
    'https://05dd-2607-fb91-11af-8951-c2b-b888-dca-91fb.ngrok-free.app',  # New ngrok URL
    'https://*.railway.app',  # Add this for all Railway subdomains
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # Using pathlib syntax


LOGIN_URL = '/login/'  # or whatever your login URL is




INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  
    'website',
    'multiselectfield',
    'whitenoise.runserver_nostatic',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = 'PulseProject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'website.context_processors.tenant_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'PulseProject.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

# Static files configuration
STATIC_URL = '/static/' 

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'website/static'),
]

# White noise static storage
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Google OAuth - First check environment variables, then fallback to file
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')

# Set the client secret path (only used in development mode)
GOOGLE_OAUTH_CLIENT_SECRET_PATH = os.path.join(BASE_DIR, os.getenv('GOOGLE_OAUTH_CLIENT_SECRET_PATH', 'secrets/client_secret.json'))

# Only try to read from file if environment variables are not set and we're in development mode
if (not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET) and ENVIRONMENT == 'development':
    try:
        with open(GOOGLE_OAUTH_CLIENT_SECRET_PATH, 'r') as f:
            client_secrets = json.load(f)
            GOOGLE_OAUTH_CLIENT_ID = client_secrets['web']['client_id']
            GOOGLE_OAUTH_CLIENT_SECRET = client_secrets['web']['client_secret']
    except (FileNotFoundError, KeyError):
        if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET:
            print("Warning: Google OAuth client secrets not configured")

GOOGLE_OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/adwords',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid'
]

# Google Ads API settings
GOOGLE_ADS_API_VERSION = None  # Let the client library determine the latest available version
GOOGLE_ADS_ENDPOINT = None  # Use the default endpoint
USE_MOCK_GOOGLE_ADS = False  # Set to True only for development

# Add this to get a Google Ads developer token from environment variable
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN')




#
#
# Middleware and Error Handling
#
#


# Configure custom error handlers
handler404 = 'website.error_handlers.handler404'
handler500 = 'website.error_handlers.handler500'
handler403 = 'website.error_handlers.handler403'
handler400 = 'website.error_handlers.handler400'

# Configure logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'django.log'),
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'propagate': True,
        },
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'website': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
log_dir = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)



#
#
# End Middleware and Error Handling
#
#
DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.spatialite',
        'NAME': 'neo.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'KEY_PREFIX': 'neo_test',
    }
}

AUTHENTICATION_BACKENDS = (
    'neo.backends.NeoMultiBackend',
    'django.contrib.auth.backends.ModelBackend',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'neo.middleware.NeoMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',     
    'django.middleware.transaction.TransactionMiddleware',
)

# A tuple of callables that are used to populate the context in RequestContext. 
# These callables take a request object as their argument and return a 
# dictionary of items to be merged into the context.
TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.core.context_processors.request",
    'preferences.context_processors.preferences_cp',
    'foundry.context_processors.foundry',
)

FOUNDRY = {
    'layers': ('basic', )
}

# AppDirectoriesTypeLoader must be after filesystem loader
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'foundry.loaders.AppDirectoriesTypeLoader',
    'django.template.loaders.app_directories.Loader',
)

INSTALLED_APPS = [
    'atlas',
    'django.contrib.auth',
    'django.contrib.comments',
    'django.contrib.contenttypes',
    'django.contrib.sites',
    'django.contrib.gis',
    'django.contrib.sessions',
    'category',
    'preferences',
    'jmbo',
    'competition',
    'photologue',
    'secretballot',
    'publisher',
    'foundry',
    'neo',
    'compressor',
    'social_auth',
]

NEO = {
    'URL': 'https://neostaging.wsnet.diageo.com/MCAL/MultiChannelWebService.svc',
    'APP_ID': '',
    'VERSION_ID': '1.3',
    'PROMO_CODE': '',
    'PASSWORD': '',
    'BRAND_ID': 0,
    'VERIFY_CERT': False,
    'USE_MCAL': True,
}

STATIC_URL = 'static/'

SITE_ID = 1

ROOT_URLCONF = 'neo.test_urls'

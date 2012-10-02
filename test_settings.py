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
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'neo_test',
    }
}

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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
]
#'URL': 'https://neostaging.wsnet.diageo.com/MCAL/MultiChannelWebService.svc',
NEO = {
    'URL': 'https://209.207.228.8/neowebservices',
    'APP_ID': '35001',
    'VERSION_ID': '1.3',
    'PROMO_CODE': 'testPromo',
    'BRAND_ID': 12,
    'VERIFY_CERT': False,
}

STATIC_URL = 'static/'

SITE_ID = 1

ROOT_URLCONF = 'neo.urls'

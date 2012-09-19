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
    'photologue',
    'secretballot',
    'publisher',
    'foundry',
    'neo',
]
#'URL': 'https://neostaging.wsnet.diageo.com/MCAL/MultiChannelWebService.svc',
NEO = {
    'URL': 'https://neostaging.wsnet.diageo.com/MCAL/MultiChannelWebService.svc',
    'APP_ID': '67125',
    'VERSION_ID': '1.3',
    'PROMO_CODE': 'testPromo',
    'BRAND_ID': 12,
    'PASSWORD': 'PraJWTRegApp@67125_19092011',
}

STATIC_URL = 'static/'

SITE_ID = 1

ROOT_URLCONF = 'neo.urls'
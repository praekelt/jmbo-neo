from django.conf.urls.defaults import patterns, url, include

urlpatterns = patterns('',
    (r'^', include('neo.urls')),
    (r'^', include('competition.urls')),
)

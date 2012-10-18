from setuptools import setup, find_packages

setup(
    name='jmbo-neo',
    version='0.1',
    description='Jmbo Neo Web Services integration app.',
    long_description = open('README.rst', 'r').read() + open('AUTHORS.rst', 'r').read() + open('CHANGELOG.rst', 'r').read(),
    author='Praekelt International',
    author_email='dev@praekelt.com',
    license='BSD',
    url='http://github.com/praekelt/jmbo-neo',
    packages = find_packages(),
    dependency_links = [
        'http://github.com/praekelt/jmbo-foundry/tarball/develop/2.6.praekelt#egg=jmbo-foundry-2.6.praekelt',
        'http://github.com/praekelt/jmbo-competition/tarball/feature/competition_entry_form/2.6.praekelt#egg=jmbo-competition-2.6.praekelt',
    ],
    install_requires = [
	'jmbo-foundry',
        'django-ckeditor',
        'requests',
        'lxml',
        'django>=1.4',
    ],
    tests_require=[
	'django-setuptest',
        'python-memcached',
    ],
    test_suite="setuptest.setuptest.SetupTestSuite",
    include_package_data=True,
    classifiers = [
        "Programming Language :: Python",
        "License :: OSI Approved :: BSD License",
        "Development Status :: 4 - Beta",
        "Operating System :: OS Independent",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    zip_safe=False,
)

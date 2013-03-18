from setuptools import setup, find_packages

setup(
    name='jmbo-neo',
    version='0.3',
    description='Jmbo Neo Web Services integration app.',
    long_description = open('README.rst', 'r').read() + open('AUTHORS.rst', 'r').read() + open('CHANGELOG.rst', 'r').read(),
    author='Praekelt International',
    author_email='dev@praekelt.com',
    license='BSD',
    url='http://github.com/praekelt/jmbo-neo',
    packages = find_packages(),
    install_requires = [
	    'jmbo-foundry==1.1.15',
        'django-ckeditor',
        'requests',
        'lxml',
        'django>=1.4,<1.5',
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

from setuptools import setup, find_packages


def getcmdclass():
    try:
        from setuptest import test
        return test
    except ImportError:
        return None


setup(
    name='jmbo-neo',
    version='0.4.5.1',
    description='Jmbo Neo Web Services integration app.',
    long_description = open('README.rst', 'r').read() + open('AUTHORS.rst', 'r').read() + open('CHANGELOG.rst', 'r').read(),
    author='Praekelt International',
    author_email='dev@praekelt.com',
    license='BSD',
    url='http://github.com/praekelt/jmbo-neo',
    packages = find_packages(),
    install_requires = [
        'jmbo-foundry>=1.1.15,<1.3',
        'django-ckeditor',
        'requests',
        'lxml',
        'django>=1.4,<1.5',
        'mock'
    ],
    tests_require=[
        'django-setuptest',
    ],
    test_suite="setuptest.setuptest.SetupTestSuite",
    cmdclass={'test': getcmdclass()},
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

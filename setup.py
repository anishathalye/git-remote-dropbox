from setuptools import setup
from codecs import open # For a consistent encoding
from os import path
import re


here = path.dirname(__file__)


with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


def read(*names, **kwargs):
    with open(
        path.join(here, *names),
        encoding=kwargs.get("encoding", "utf8")
    ) as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name='git-remote-dropbox',

    version=find_version('git_remote_dropbox', '__init__.py'),

    description='A transparent bidirectional bridge between Git and Dropbox',
    long_description=long_description,

    url='https://github.com/anishathalye/git-remote-dropbox',

    author='Anish Athalye',
    author_email='me@anishathalye.com',

    license='MIT',

    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Version Control',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='git dropbox',

    packages=['git_remote_dropbox'],

    install_requires=['dropbox>=6.1,<7'],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'git-remote-dropbox=git_remote_dropbox:main',
        ],
    },
)

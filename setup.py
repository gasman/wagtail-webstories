from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="wagtail-webstories",
    version="0.1.1",
    packages=find_packages(exclude=('tests', 'tests.*')),
    include_package_data=True,
    test_suite="tests",
    url="https://github.com/torchbox/wagtail-webstories/",

    author="Matt Westcott",
    author_email="matthew@torchbox.com",
    description="AMP web story support for Wagtail",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.0",
        "Framework :: Wagtail",
        "Framework :: Wagtail :: 5",
        "Framework :: Wagtail :: 6",
        "Topic :: Internet :: WWW/HTTP",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "wagtail>=5.2",
        "webstories>=0.0.1,<1",
        "requests>=2.24.0,<3",
        "beautifulsoup4>=4.6,<5",
    ],
    extras_require={
        "testing": [
            "responses>=0.12,<1",
            "Pillow>=4.0.0,<11.0.0",
            "wagtailmedia>=0.6,<0.16",
        ]
    },
    license="BSD",
)

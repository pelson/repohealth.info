import setuptools

setuptools.setup(
    name="repohealth",
    version="1.0",
    author="Philip Elson",
    author_email="pelson.pub@gmail.com",
    description="Get vital statistics on a GitHub repository",
    url="https://github.com/pelson/repohealth.info",
    packages=setuptools.find_packages(),
    install_requires=[
        'plotly>=1.12.12',
        'tornado',
        'pandas',
        'requests',
        'numpy',
        'nbformat',
        'fasteners',
        'jinja2',
        'gitpython',
        'pygithub',
        'tornado',
        'tweepy',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

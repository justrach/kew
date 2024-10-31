from setuptools import setup, find_packages

setup(
    name="kew",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "typing;python_version<'3.5'",
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="A flexible async task queue manager for Python applications",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)

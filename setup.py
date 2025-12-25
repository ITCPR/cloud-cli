"""Setup script for itcpr."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="itcpr",
    version="2.1.9",
    description="CLI tool for syncing GitHub repositories from ITCPR Cloud",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="ITCPR",
    author_email="info@itcpr.org",
    url="https://itcpr.org",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "requests>=2.28.0",
        "keyring>=23.0.0",
        "tomli-w>=1.0.0",
        "PyYAML>=6.0",
    ],
    # Optional dependencies
    extras_require={
        "dev": ["pytest", "black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "itcpr=itcpr.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)


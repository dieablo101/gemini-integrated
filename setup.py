#!/usr/bin/env python3
"""Setup script for gemini-integrated pip package."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gemini-integrated",
    version="1.0.0",
    author="Kyle Gallagher",
    description="Autonomous Bilateral Terminal Console and LLM Developer Tool powered by Google Gemini and Textual",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dieablo101/gemini-integrated",
    packages=find_packages(include=["gemini_app", "gemini_app.*"]),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "textual>=0.50.0",
        "google-genai>=1.0.0",
        "rich>=13.0.0",
        "pyperclip>=1.8.0",
    ],
    entry_points={
        "console_scripts": [
            "gemini-integrated=gemini_app.main:main",
            "gemini=gemini_app.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
)

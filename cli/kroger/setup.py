from setuptools import find_namespace_packages, setup

setup(
    name="cli-web-kroger",
    version="0.1.0",
    description="CLI for Kroger",
    packages=find_namespace_packages(include=["cli_web.*"]),
    package_data={"": ["skills/*.md", "*.md"]},
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
        "playwright>=1.40",
        "rich>=13.0",
        "prompt_toolkit>=3.0",
    ],
    
    entry_points={
        "console_scripts": [
            "cli-web-kroger=cli_web.kroger.kroger_cli:main",
        ],
    },
)

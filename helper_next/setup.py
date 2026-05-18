from setuptools import find_packages, setup


setup(
    name="helper-next",
    version="0.1.0",
    description="Local web interface prototype for Helper",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={"helper_next": ["web/static/*"]},
    install_requires=[
        "fastapi>=0.83,<0.84",
        "uvicorn>=0.16,<0.17",
    ],
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "helper-next=helper_next.cli:main",
        ],
    },
)

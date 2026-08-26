from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="zerg-sdk",
    version="0.1.0",
    description="Python SDK for the HITBOT Z-ERG-20C rotating electric gripper",
    long_description=(Path(__file__).parent / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=("test", "test.*")),
    python_requires=">=3.9",
    install_requires=["pyserial>=3.5"],
    extras_require={"test": ["pytest>=7"]},
    author="ZERG SDK contributors",
    license="Apache-2.0",
)

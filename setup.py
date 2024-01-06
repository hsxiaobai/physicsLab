# -*- coding: utf-8 -*-
import setuptools

with open("./README_zh.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="physicsLab",
    version="1.4.2",
    license="MIT",
    author="Goodenough",
    author_email="2381642961@qq.com",
    description="Python API for physics-lab-AR",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitee.com/script2000/physicsLab",
    packages=setuptools.find_packages(),
    install_requires=["mido"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: Chinese (Simplified)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)

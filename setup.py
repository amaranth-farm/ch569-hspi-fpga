from setuptools import setup, find_packages


def scm_version():
    def local_scheme(version):
        return version.format_choice("+{node}", "+{node}.dirty")
    return {
        "relative_to": __file__,
        "version_scheme": "guess-next-dev",
        "local_scheme": local_scheme,
    }

setup(
    name="hspi",
    use_scm_version=scm_version(),
    author="Hans Baier",
    author_email="hansfbaier@gmail.com",
    description="CH56x HSPI FPGA interface written in amaranth HDL",
    license="Apache License 2.0",
    setup_requires=["wheel", "setuptools", "setuptools_scm"],
    install_requires=[
        "amaranth>=0.2,<=4",
        "importlib_metadata; python_version<'3.10'",
    ],
    packages=find_packages(),
    project_urls={
        "Source Code": "https://github.com/amaranth-community-unofficial/ch569-hspi-fpga",
        "Bug Tracker": "https://github.com/amaranth-community-unofficial/ch569-hspi-fpga/issues",
    },
)


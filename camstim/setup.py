from setuptools import find_packages, setup

packages = find_packages()

setup(
    name="camstim",
    version="0.2.4",
    description="camstim python package",
    author="derricw",
    author_email="derricw@alleninstitute.org",
    url="http://stash.corp.alleninstitute.org/projects/ENG/repos/camstim/browse",
    packages=packages,
    requires=['camstim'],
    install_requires=[
        "numpy>=1.11.0",
        "scipy>=1.0.0",
        "pillow>=5.0.0",
        "PyOpenGL>=3.1.0",
        "psychopy==1.82.01",
        "pyglet==1.2.4",
        "psutil>=5",
        "PyDAQmx>=1.4",
        "qtpy>=1.3.1",
        "pypiwin32",
        "pyside>=1.2.4",
        "pyyaml",
    ],
    entry_points = {
        'console_scripts': [
            'camstim_agent = camstim.zro.agent:main'
        ],
    },
    include_package_data=True,
    package_data={
        "": ['*.png', '*.ico', '*.jpg', '*.jpeg'],
    },
)

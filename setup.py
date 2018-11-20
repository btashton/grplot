"""
grplot
"""
from setuptools import setup

setup(
    name='grplot',
    version='0.1',
    url='https://github.com/btashton/grplot',
    license='BSD',
    author='Brennan Ashton',
    author_email='bashton@brennanashton.com',
    description='Plotting tool for GNU Radio',
    long_description=__doc__,
    py_modules=[
        'grplot'
    ],
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=[
        'numpy>=1.12.0',
        'scipy>=1.0.0',
        'pyqtgraph>=0.10.0',
        'PyQt5>=5.10',
    ],
    entry_points={
        'console_scripts': [
            'grplot = grplot:main',
        ],
    },
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ]
)

# grplot

This is an out of tree plotting tool that replaces gr_plot_qt.  The old tool was python2 only because of old requirements.  This implementation uses pyqtgraph to perform most of the plotting logic, and PyQT5 to provide the underlying GUI.  This is a simple GUI, so the use of `QT Designer` has also been dropped.

The math heavy lifting is all contained within `numpy`.

## Features
* Analysis of gnuradio binary sink files
* Multiple plot views including: Time Series (IQ), PSD, Spectrogram
* File seek

## Usage
From the command line just run:
`grplot`

## Installation

* For development: `pip install -e .`
* For release: `pip install .`

## Development
To help keep the quality up, please make sure all tests and linters pass:
* pytest
* pylint
* pycodestyle [formerly pep8]

Also try and use python types whenever possible.  Because this code still needs to support python2, please use use the comment style for now.

The project is setup to support pipenv to make setting the project up easier.
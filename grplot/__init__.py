"""grplot utility.
Provides a QT application for plotting gnuradio data.

Example:
    $ python -m grplot
"""
try:
    from typing import (
        Optional, Tuple,
    )
except ImportError:
    # Typing is needed for mypy on python2
    pass

import sys
import os
import logging

import pyqtgraph as pg  # type: ignore
import numpy  # type: ignore
from scipy import signal  # type: ignore
from PyQt5 import QtGui
from PyQt5.QtGui import (
    QIcon,
)
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QLabel, QWidget, QTabWidget, QVBoxLayout,
    QLineEdit, QComboBox, QGridLayout, QFormLayout, qApp, QAction,
    QFileDialog, QGroupBox, QSpinBox,
)

logger = logging.getLogger(__name__)


# These window functions come from `scipy.signal.windows`.  Some are excluded
# because they require additional parameters.  Perhaps these could be supported
# by extending the window function UI to take in the required parameters
_WINDOW_FUNCTIONS = [
    'boxcar', 'triang', 'blackman', 'hamming', 'hann', 'bartlett',
    'flattop', 'parzen', 'bohman', 'blackmanharris', 'nuttall',
    'barthann',
]


class PlotSettingsWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        file_info = QGroupBox('File Info:')
        file_layout = QFormLayout()
        file_info.setLayout(file_layout)
        file_name = QLabel('No File')
        file_length = QLabel('Unknown')
        file_duration = QLabel('Unknown')
        file_data_type = QComboBox()

        # This list could be extended further, or maybe read from numpy
        # custom ones could be created via `numpy.dtype`
        file_data_type.addItems([
            'complex64', 'complex128',
            'float32', 'float64',
            'int8', 'int16', 'int32', 'int64',
            'uint8', 'uint16', 'uint32', 'uint64',
        ])
        file_sr_widget = QSpinBox()
        file_sr_widget.setMinimum(0.0)
        file_sr_widget.setValue(8000)
        file_layout.addRow(QLabel('File Name'), file_name)
        file_layout.addRow(QLabel('File Length'), file_length)
        file_layout.addRow(QLabel('File Duration'), file_duration)
        file_layout.addRow(QLabel('Data Type'), file_data_type)
        file_layout.addRow(QLabel('Sample Rate'), file_sr_widget)

        fft_settings = QGroupBox('FFT:')
        fft_layout = QFormLayout()
        fft_size_widget = QComboBox()
        fft_size_widget.addItems([str(pow(2, exp)) for exp in range(7, 14)])
        fft_window_widget = QComboBox()
        fft_window_widget.addItems(_WINDOW_FUNCTIONS)
        fft_layout.addRow(QLabel('Window Function'), fft_window_widget)
        fft_layout.addRow(QLabel('Size'), fft_size_widget)
        fft_settings.setLayout(fft_layout)

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(file_info)
        settings_layout.addWidget(fft_settings)

        self.setLayout(settings_layout)


class MainWindow(QMainWindow):
    """Main window that contains the plot widget as well as the setting"""

    def __init__(self):
        # type: () -> None
        super().__init__()
        self.setWindowTitle('GNURadio Plotting Utility')
        self.setGeometry(0, 0, 1000, 500)
        self._setup_actions()
        self.statusBar()
        self._add_menu()

        # The tabs for the plots
        self.plot_widget = PlottingeWidget(self)

        self.settings_widget = PlotSettingsWidget()

        layout = QGridLayout()
        layout.addWidget(self.plot_widget, 0, 0, 1, 1)
        layout.setColumnStretch(0, 1)
        layout.addWidget(self.settings_widget, 0, 1)
        layout.setColumnMinimumWidth(0, 600)
        layout.setColumnMinimumWidth(1, 500)

        self._w = QWidget()
        self._w.setLayout(layout)
        self.setCentralWidget(self._w)

        self._data_source = DataSource()
        # We have not loaded a file yet, so let the file pick the data range
        self._first_file = True

        self.show()

    def _setup_actions(self):
        # type: () -> None
        self._exit_action = QAction('&Exit', self)
        self._exit_action.setShortcut('Ctrl+Q')
        self._exit_action.setStatusTip('Exit application')
        self._exit_action.triggered.connect(qApp.quit)

        self._open_action = QAction('&Open', self)
        self._open_action.setShortcut('Ctrl+O')
        self._open_action.setStatusTip('Open data file')
        self._open_action.triggered.connect(self._open_file)

    def _add_menu(self):
        # type: () -> None
        self._menu_bar = self.menuBar()
        file_menu = self._menu_bar.addMenu('&File')
        file_menu.addAction(self._exit_action)
        file_menu.addAction(self._open_action)

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Open File', os.getenv('HOME')
        )
        # Should throw some kind of warning message at this point
        self._data_source.load_file(file_path, self._first_file)
        self.plot_widget.refresh_plot(self._data_source)


class PlottingeWidget(QWidget):
    """Container widget class that stores the different plots under
    a tab widget. This also contains the interfaces for controlling
    the data that is being shown"""

    def __init__(self, parent):
        # type: (QWidget) -> None

        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Initialize tab screen
        tabs = QTabWidget()

        self.plot_time = pg.PlotWidget()
        self.plot_time.addLegend()
        self.plot_psd = pg.PlotWidget()
        self.plot_spec = pg.PlotWidget()
        spec_image = pg.ImageItem()
        self.plot_spec.addItem(spec_image)

        self.plot_curves = {
            'real': self.plot_time.plot(pen='b', name='I'),
            'imag': self.plot_time.plot(pen='r', name='Q'),
            'psd': self.plot_psd.plot(pen='b'),
            'spec': spec_image,
        }

        for _, plot in self.plot_curves.items():
            # Default to using the mouse for selecting region instead of pan
            # this can be change by the user by right clicking and selecting
            # the menu item
            plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)

        self.plot_time.getAxis('bottom').setLabel('Time', units='s')
        self.plot_time.getAxis('bottom').enableAutoSIPrefix(False)
        # This is not rendering correctly
        self.plot_time.getAxis('left').setLabel('Amplitude', unit='V')

        self.plot_psd.getAxis('bottom').setLabel('Frequency', units='Hz')
        self.plot_psd.getAxis('left').setLabel('Magnitude', units='dB')

        self.plot_spec.getAxis('bottom').setLabel('Frequency', units='Hz')
        # The auto prefix is messed up on this kind of plot, might have
        # to do with the scaling factors that are applied
        self.plot_spec.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_spec.getAxis('left').setLabel('Time', units='s')
        self.plot_spec.getAxis('left').enableAutoSIPrefix(False)

        tabs.addTab(self.plot_time, "Time (iq)")
        tabs.addTab(self.plot_psd, "PSD")
        tabs.addTab(self.plot_spec, "Spectrogram")

        # Add tabs to widget
        layout.addWidget(tabs)
        self.setLayout(layout)

        self.fftsize = 256

    def refresh_plot(self, data_source):
        # type: (DataSource) -> None
        # Need to look up the correct tab here for now just plot timeseries
        self._refresh_time_plot(data_source)
        self._refresh_psd_plot(data_source)
        self._refresh_spec_plot(data_source)

    def _refresh_time_plot(self, data):
        # type: (DataSource) -> None
        self.plot_curves['real'].setData(data.time, data.data.real)
        self.plot_curves['imag'].setData(data.time, data.data.imag)

    def _refresh_psd_plot(self, data):
        # Hard code the window function for now
        window = numpy.blackman(self.fftsize)
        freq_segments, power_d = signal.welch(
            data.data,
            fs=data.sample_rate,
            window=window,
            nfft=self.fftsize,
            noverlap=self.fftsize/4.0,
            scaling='density',
            return_onesided=False,  # Complex only right now so must be False
        )
        power_d_log = 10.0*numpy.log10(abs(power_d))
        self.plot_curves['psd'].setData(freq_segments, power_d_log)

    def _refresh_spec_plot(self, data):
        # Hard code the window function for now
        window = numpy.blackman(self.fftsize)
        freq_segments, time_segments, spec = signal.spectrogram(
            data.data,
            fs=data.sample_rate,
            window=window,
            nfft=self.fftsize,
            noverlap=self.fftsize/4.0,
            # Should we use density? matplotlib was using spectrum scaling
            scaling='spectrum',
            return_onesided=False,  # Complex only right now so must be False
        )
        spec = 10.0*numpy.log10(abs(spec))

        freq_segments = numpy.fft.fftshift(freq_segments)
        spec = numpy.fft.fftshift(spec, axes=0)
        self.plot_curves['spec'].setImage(spec)

        f_scale = (freq_segments[-1] - freq_segments[0]) / len(freq_segments)
        t_scale = (time_segments[-1] - time_segments[0]) / len(time_segments)

        pos = (freq_segments[0], time_segments[0])

        self.plot_curves['spec'].translate(*pos)
        self.plot_curves['spec'].scale(f_scale, t_scale)


class DataSource(object):
    """Data interface class for plotting"""

    def __init__(self, path=None):
        self._data_type = numpy.complex64
        self._source_path = None  # type: Optional[str]
        self.data = numpy.array([], dtype=numpy.complex64)
        self._start = 0  # type: int
        self._end = 0  # type: int
        self.sample_rate = 8000.0  # type: float
        if path is not None:
            self.load_file(path, True)

    def _file_range(self, file_len, full_scale=False):
        # type: (int, bool) -> Tuple[int, int]
        data_size = numpy.dtype(self._data_type).itemsize

        remainder_bytes = file_len % data_size
        if remainder_bytes != 0:
            logger.warning(
                'Unexpected file length. Data size %d does not pack into'
                '%d bytes. File will be truncated',
                data_size, file_len
            )
            file_len -= remainder_bytes
        data_len = int(file_len/data_size)

        if data_len == 0:
            # The file is too short to do anything useful
            raise Exception(
                'File is too short.  Needed at least {0} bytes'
                .format(data_size)
            )

        if full_scale:
            return 0, data_len

        new_start = self._start  # type: int
        new_end = self._end  # type: int

        if new_start >= data_len:
            new_start = data_len - 1

        if new_end > data_len:
            new_end = data_len

        return new_start, new_end

    def load_file(self, path, reset=False):
        # type: (str, bool) -> None
        """Update the source data file return if the ui needs to be updated"""
        with open(path, 'rb') as data_file:
            file_len = os.fstat(data_file.fileno()).st_size  # type: int

            new_start, new_end = self._file_range(file_len, reset)

            limits_changed = (new_start, new_end) != (self._start, self._end)
            if limits_changed and not reset:
                # Only log if limits changed unexpectedly
                logger.warning(
                    'Limits out of range [%d, %d] adjusted to [%d, %d]',
                    self._start, self._end, new_start, new_end
                )

            data_size = numpy.dtype(self._data_type).itemsize
            data_file.seek(new_start*data_size)
            self.data = numpy.fromfile(
                data_file, self._data_type, new_end-new_start
            )

            # The data was loaded apply the state
            self._start = new_start
            self._end = new_end
            self._source_path = path

    def reload_file(self):
        """Reprocess data file"""
        self.load_file(self._source_path)

    @property
    def start(self):
        # type: () -> int
        """Start point in data file"""
        return self._start

    @start.setter
    def start(self, value):
        # type: (int) -> None
        try:
            old_start = self._start
            self._start = value
            self.reload_file()
        except Exception:
            self._start = old_start
            raise

    @property
    def end(self):
        # type: () -> int
        """End point in data file"""
        return self._end

    @end.setter
    def end(self, value):
        # type: (int) -> None
        try:
            old_end = self._end
            self._end = value
            self.reload_file()
        except Exception:
            self._end = old_end
            raise

    @property
    def time(self):
        time_range = numpy.linspace(self.start, self.end, len(self.data), True)
        time_range *= self.sample_rate
        return time_range


def main():
    # type: () -> None
    """Main console entry point"""
    # setup logger
    logging.basicConfig()
    app = QApplication(sys.argv)

    # Need to prevent the window object form being cleaned up while execution
    # loop is running
    _qt_window = MainWindow()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

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
logger.setLevel(logging.DEBUG)


# These window functions come from `scipy.signal.windows`.  Some are excluded
# because they require additional parameters.  Perhaps these could be supported
# by extending the window function UI to take in the required parameters
_WINDOW_FUNCTIONS = [
    'boxcar', 'triang', 'blackman', 'hamming', 'hann', 'bartlett',
    'flattop', 'parzen', 'bohman', 'blackmanharris', 'nuttall',
    'barthann',
]


class FileSettingsWidget(QGroupBox):
    """Widget that holds information and settings for a data source"""
    def __init__(self, title, change_cb, sample_rate=8000):
        QGroupBox.__init__(self, title)

        # This is really just a cached value for computing duration
        self._samples = None

        self._name_w = QLabel('No File')
        self._length_w = QLabel('Unknown')
        self._duration_w = QLabel('Unknown')

        self._data_type_w = QComboBox()
        # This list could be extended further, or maybe read from numpy
        # custom ones could be created via `numpy.dtype`
        self._data_type_w.addItems([
            'complex64', 'complex128',
            'float32', 'float64',
            'int8', 'int16', 'int32', 'int64',
            'uint8', 'uint16', 'uint32', 'uint64',
        ])
        self._data_type_w.currentIndexChanged.connect(change_cb)

        self._sample_rate_w = QSpinBox()
        self._sample_rate_w.setMinimum(0.0)
        self._sample_rate_w.setMaximum(1000000)  # Can there be no max?
        self._sample_rate_w.setValue(sample_rate)
        self._sample_rate_w.valueChanged.connect(change_cb)
        self._sample_rate_w.valueChanged.connect(self._update_duration)

        layout = QFormLayout()
        layout.addRow(QLabel('File Name'), self._name_w)
        layout.addRow(QLabel('File Length'), self._length_w)
        layout.addRow(QLabel('File Duration'), self._duration_w)
        layout.addRow(QLabel('Data Type\n(not_implemented)'), self._data_type_w)
        layout.addRow(QLabel('Sample Rate'), self._sample_rate_w)
        self.setLayout(layout)

    def _update_duration(self):
        duration = 'Unknown'
        if self._samples is not None:
            duration = str(self._samples / self.sample_rate)
        self._duration_w.setText(duration)

    @property
    def sample_rate(self):
        return float(self._sample_rate_w.value())

    @sample_rate.setter
    def sample_rate(self, rate):
        self._sample_rate_w.setValue(rate)
        self._update_duration()

    def _set_file_name(self, value):
        self._name_w.setText(value)

    def _set_file_len(self, value):
        self._samples = value
        self._length_w.setText(str(value))
        self._update_duration()

    file_name = property(None, _set_file_name)
    file_length = property(None, _set_file_len)


class FFTSettingsWidget(QGroupBox):
    def __init__(self, title, change_cb):
        QGroupBox.__init__(self, title)
        self._size_w = QComboBox()
        self._size_w.addItems([str(pow(2, exp)) for exp in range(7, 14)])
        self._size_w.currentIndexChanged.connect(change_cb)
        self._window_w = QComboBox()
        self._window_w.addItems(_WINDOW_FUNCTIONS)
        self._window_w.setCurrentIndex(_WINDOW_FUNCTIONS.index('blackman'))
        self._window_w.currentIndexChanged.connect(change_cb)

        fft_layout = QFormLayout()
        fft_layout.addRow(QLabel('Window Function'), self._window_w)
        fft_layout.addRow(QLabel('Size'), self._size_w)
        self.setLayout(fft_layout)

    @property
    def fft_size(self):
        return int(self._size_w.currentText())

    @property
    def fft_window(self):
        return self._window_w.currentText()


class PlotSettingsWidget(QWidget):
    def __init__(self, plot_widget):
        QWidget.__init__(self)

        self._plot_widget = plot_widget
        self._file_info = FileSettingsWidget('File Info:', self._file_change)

        # Construct the fft settings
        self._fft_settings = FFTSettingsWidget('FFT:', self._fft_change)


        # Add setting groups to settings box
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self._file_info)
        settings_layout.addWidget(self._fft_settings)
        self.setLayout(settings_layout)

        # Reflect the settings down
        self._file_change()
        self._fft_change()

    def _file_change(self):
        self._plot_widget.sample_rate = self._file_info.sample_rate
        logger.debug("Sample rate updated: %d", self._file_info.sample_rate)

    def _fft_change(self):
        logger.debug(
            "FFT Settings updated:\n\tSize: %d\n\tWindow %s",
            self._fft_settings.fft_size, self._fft_settings.fft_window,
        )
        self._plot_widget.set_fft(
            self._fft_settings.fft_size, self._fft_settings.fft_window
        )

    def source_update(self):
        # The source data has been updated, the settings widget needs
        # to be updated to reflect this change
        self._file_info.file_name = self._plot_widget.data_source.source_path
        self._file_info.file_length = len(self._plot_widget.data_source.data)


class PlottingeWidget(QWidget):
    """Container widget class that stores the different plots under
    a tab widget. This also contains the interfaces for controlling
    the data that is being shown"""

    def __init__(self, parent, data_source=None):
        # type: (QWidget, Optional[DataSource]) -> None

        super().__init__(parent)
        self._data_source = data_source
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

        self.plot_time.getAxis('bottom').setLabel('Time (s)')
        self.plot_time.getAxis('left').setLabel('Amplitude (V)')

        self.plot_psd.getAxis('bottom').setLabel('Frequency (Hz)')
        self.plot_psd.getAxis('left').setLabel('Magnitude (dB)')

        self.plot_spec.getAxis('bottom').setLabel('Frequency (Hz)')
        self.plot_spec.getAxis('left').setLabel('Time (s)')

        tabs.addTab(self.plot_time, "Time (IQ)")
        tabs.addTab(self.plot_psd, "PSD")
        tabs.addTab(self.plot_spec, "Spectrogram")

        # Add tabs to widget
        layout.addWidget(tabs)
        self.setLayout(layout)

        # These should be overwritten by a settings widget
        self.fftsize = 256
        self.window = signal.windows.blackman(self.fftsize)
        self._sample_rate = 8000

    def refresh_plot(self):
        # type: (DataSource) -> None
        # Need to look up the correct tab here for now just plot timeseries
        if self._data_source is not None and self._data_source.data is not None:
            self._refresh_time_plot(self._data_source)
            self._refresh_psd_plot(self._data_source)
            self._refresh_spec_plot(self._data_source)

    def _refresh_time_plot(self, data):
        # type: (DataSource) -> None
        time_range = data.time_range(self._sample_rate)
        self.plot_curves['real'].setData(time_range, data.data.real)
        self.plot_curves['imag'].setData(time_range, data.data.imag)

    def _refresh_psd_plot(self, data):
        freq_segments, power_d = signal.welch(
            data.data,
            fs=self.sample_rate,
            window=self.window,
            nfft=self.fftsize,
            noverlap=self.fftsize/4.0,
            scaling='density',
            return_onesided=False,  # Complex only right now so must be False
        )
        power_d_log = 10.0*numpy.log10(abs(power_d))
        freq_segments = numpy.fft.fftshift(freq_segments)
        power_d_log = numpy.fft.fftshift(power_d_log)
        self.plot_curves['psd'].setData(freq_segments, power_d_log)

    def _refresh_spec_plot(self, data):
        # Hard code the window function for now
        freq_segments, time_segments, spec = signal.spectrogram(
            data.data,
            fs=self._sample_rate,
            window=self.window,
            nfft=self.fftsize,
            noverlap=self.fftsize/4.0,
            scaling='spectrum',
            return_onesided=False,
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

    @property
    def data_source(self):
        return self._data_source

    @property
    def sample_rate(self):
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, rate):
        # This is just controlling the plots. This does not control an settings
        # widget
        self._sample_rate = rate
        self.refresh_plot()

    def set_fft(self, size, window):
        self.fftsize = size
        # Might be possible to use the signal.windows.get_window function
        # but it would require some additional logic to normalize it
        self.window = getattr(signal.windows, window)(size)
        self.refresh_plot()


class DataSource(object):
    """Data interface class for plotting"""

    def __init__(self, path=None):
        self._data_type = numpy.complex64
        self.source_path = None  # type: Optional[str]
        self.data = None
        self._start = 0  # type: int
        self._end = 0  # type: int
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
            self.source_path = path

    def reload_file(self):
        """Reprocess data file"""
        self.load_file(self.source_path)

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

    def time_range(self, sample_rate):
        t_range = numpy.linspace(self.start, self.end, len(self.data), True)
        t_range *= sample_rate
        return t_range


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


        self._data_source = DataSource()
        # We have not loaded a file yet, so let the file pick the data range
        self._first_file = True

        # The tabs for the plots
        self.plot_widget = PlottingeWidget(self, self._data_source)

        self.settings_widget = PlotSettingsWidget(self.plot_widget)

        layout = QGridLayout()
        layout.addWidget(self.plot_widget, 0, 0, 1, 1)
        layout.setColumnStretch(0, 1)
        layout.addWidget(self.settings_widget, 0, 1)
        layout.setColumnMinimumWidth(0, 600)
        layout.setColumnMinimumWidth(1, 500)

        self._w = QWidget()
        self._w.setLayout(layout)
        self.setCentralWidget(self._w)

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
        self.settings_widget.source_update()
        self.plot_widget.refresh_plot()


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

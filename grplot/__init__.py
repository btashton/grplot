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
from collections import namedtuple

import pyqtgraph as pg  # type: ignore
import numpy  # type: ignore
import click
from scipy import signal  # type: ignore
from PyQt5.QtCore import QSize
from PyQt5 import QtGui
from PyQt5.QtGui import (
    QIcon, QColor
)
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QLabel, QWidget, QTabWidget, QVBoxLayout,
    QLineEdit, QComboBox, QGridLayout, QFormLayout, qApp, QAction,
    QFileDialog, QColorDialog, QGroupBox, QDoubleSpinBox, QPushButton
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


class FileSettingsWidget(QGroupBox):
    """Widget that holds information and settings for a data source"""
    def __init__(self, title, change_cb, sample_rate=8000):
        QGroupBox.__init__(self, title)

        # This is really just a cached value for computing duration
        self._samples = None

        self._change_cb = change_cb

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

        self._sample_rate_w = QDoubleSpinBox()
        self._sample_rate_w.setMinimum(0.0)
        self._sample_rate_w.setMaximum(1000000)  # Can there be no max?
        self._sample_rate_w.setValue(sample_rate)
        self._sample_rate_w.valueChanged.connect(self._sample_rate_change)

        layout = QFormLayout()
        layout.addRow(QLabel('File Name'), self._name_w)
        layout.addRow(QLabel('File Length'), self._length_w)
        layout.addRow(QLabel('File Duration'), self._duration_w)
        layout.addRow(QLabel('Data Type\n(TODO)'), self._data_type_w)
        layout.addRow(QLabel('Sample Rate'), self._sample_rate_w)
        self.setLayout(layout)

    def _sample_rate_change(self):
        if float(self._sample_rate_w.value()) > 0:
            self._change_cb()
            self._update_duration()

        # else maybe we try and bump this value back up, or show a warning icon

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
        if rate > 0:
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


class ColorWellWidget(QPushButton):
    def __init__(self, size=QSize(50, 40), color=QColor(0, 0, 0)):
        QPushButton.__init__(self)
        self._color = color
        self._color_picker = QColorDialog()
        self.setFixedSize(size)
        self.setAutoFillBackground(True)
        self.set_color(color)
        self.clicked.connect(self._clicked_cb)
        self._callbacks = []

    def set_color(self, color):
        palette = self.palette()
        role = self.backgroundRole()
        palette.setColor(role, color)
        self.setPalette(palette)
        self._color = color

    def _clicked_cb(self, event):
        self._color_picker.setCurrentColor(self._color)
        self.set_color(self._color_picker.getColor())
        for callback in self._callbacks:
            callback(self._color)

    def connect(self, callback):
        self._callbacks.append(callback)


class PlotStyleWidget(QGroupBox):
    """Standard style interface for a pyqtplot PlotItem"""
    def __init__(self, plot):
        QGroupBox.__init__(self, plot.name())

        self._plot = plot
        self._symbol_map = {
            'none': None,
            'circle': 'o',
            'square': 's',
            'triangle': 't',
            'diamond': 'd',
            'plus': '+',
        }
        # plot.opts['pen'] is sometimes a pen and sometimes a string
        # make a pen just to be sure
        plot_pen = pg.mkPen(plot.opts['pen'])
        plot_symbol = plot.opts['symbol']

        self._color_picker = ColorWellWidget(color=plot_pen.color())
        self._color_picker.connect(self._color_update)

        self._symbol_picker = QComboBox()
        self._symbol_picker.addItems(self._symbol_map.keys())

        self._symbol_picker.setCurrentText('none')
        for text, symbol in self._symbol_map.items():
            if plot_symbol == symbol:
                self._symbol_picker.setCurrentText(text)
        self._symbol_picker.currentIndexChanged.connect(self._symbol_update)

        layout = QFormLayout()
        layout.addRow(QLabel('Curve Color'), self._color_picker)
        layout.addRow(QLabel('Curve Symbol'), self._symbol_picker)
        self.setLayout(layout)

    def _color_update(self, color):
        self._plot.setPen(pg.mkPen(color))

    def _symbol_update(self):
        symbol = self._symbol_map[self._symbol_picker.currentText()]
        self._plot.setSymbol(symbol)


class SpectrogramStyleWidget(QGroupBox):
    """Standard style interface for a pyqtplot ImageItem"""
    def __init__(self, plot, title=''):
        QGroupBox.__init__(self, title)

        self._plot = plot

        self._gradient_map = pg.graphicsItems.GradientEditorItem.Gradients
        self._gradient = QComboBox()
        self._gradient.addItems(self._gradient_map.keys())

        self._gradient.setCurrentText('grey')
        self._gradient_update()

        self._gradient.currentIndexChanged.connect(self._gradient_update)

        layout = QFormLayout()
        layout.addRow(QLabel('Gradient'), self._gradient)
        self.setLayout(layout)

    def _gradient_update(self):
        gradient = self._gradient_map[self._gradient.currentText()]
        color_map = pg.ColorMap(*zip(*gradient['ticks']))
        self._plot.setLookupTable(color_map.getLookupTable())


class PlotStyleSettingsWidget(QGroupBox):
    def __init__(self, title):
        QGroupBox.__init__(self, title)
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

    def add_plot(self, plot):
        widget = PlotStyleWidget(plot)
        self._layout.addWidget(widget)

    def add_spectrogram(self, plot, title):
        widget = SpectrogramStyleWidget(plot, title)
        self._layout.addWidget(widget)


class PlotSettingsWidget(QWidget):
    def __init__(self, plot_widget):
        QWidget.__init__(self)

        self._plot_widget = plot_widget
        self._file_info = FileSettingsWidget('File Info:', self._file_change)

        # Construct the fft settings
        self._fft_settings = FFTSettingsWidget('FFT:', self._fft_change)

        # Maybe create a few of these for each of the plots and then turn
        # them on and off
        self._plot_style_settings = PlotStyleSettingsWidget('Plot Style:')

        i_curve, q_curve = PlottingWidget.get_iq(
            self._plot_widget.get_plot('time').plot)

        if i_curve is not None:
            self._plot_style_settings.add_plot(
                i_curve
            )
        if q_curve is not None:
            self._plot_style_settings.add_plot(
                q_curve
            )
        self._plot_style_settings.add_plot(
            self._plot_widget.get_plot('psd').plot.plotItem.dataItems[0]
        )

        spec_plot = self._plot_widget.get_plot('spec').plot.plotItem
        spec_image = next(plot_item for plot_item in spec_plot.items if
                             isinstance(plot_item, pg.ImageItem))
        self._plot_style_settings.add_spectrogram(
            spec_image,
            'Spectrogram'
        )

        # Add setting groups to settings box
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self._file_info)
        settings_layout.addWidget(self._fft_settings)
        settings_layout.addWidget(self._plot_style_settings)
        self.setLayout(settings_layout)

        # Reflect the settings down
        self._file_change()
        self._fft_change()
        self.source_update()

    def _file_change(self):
        self._plot_widget.sample_rate = self._file_info.sample_rate
        logger.debug("Sample rate updated: %f", self._file_info.sample_rate)

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
        data_source = self._plot_widget.data_source
        if data_source is not None:
            self._file_info.file_name = data_source.source_path
            if data_source.data is not None:
                self._file_info.file_length = len(data_source.data)


class PlottingWidget(QWidget):
    """Container widget class that stores the different plots under
    a tab widget. This also contains the interfaces for controlling
    the data that is being shown"""

    class PlotContainer(namedtuple('PlotContainer',
                                   ['plot', 'name', 'tab_idx', 'redraw_f'],
                                   defaults=(None,))):
        def redraw(self, data):
            if self.redraw_f is not None:
                self.redraw_f(self.plot, data)

    def __init__(self, parent, data_source=None):
        # type: (QWidget, Optional[DataSource]) -> None

        super().__init__(parent)
        self._data_source = data_source
        # These should be overwritten by a settings widget
        self.fftsize = 256
        self.window = signal.windows.blackman(self.fftsize)
        self._sample_rate = 8000

        layout = QVBoxLayout(self)
        # Initialize tab screen
        self._tabs = QTabWidget()

        # Add tabs to widget
        layout.addWidget(self._tabs)
        self.setLayout(layout)

        self._plots = []

        plot_time = self._add_plot(
            plot=pg.PlotWidget(),
            name='time',
            title='Time (IQ)',
            redraw_f=self._refresh_time_plot
        )
        plot_time.plot.addLegend()
        plot_time.plot.plot(pen='b', name='I')
        plot_time.plot.plot(pen='r', name='Q')
        plot_time.plot.getAxis('bottom').setLabel('Time (s)')
        plot_time.plot.getAxis('left').setLabel('Amplitude (V)')

        plot_psd = self._add_plot(
            plot=pg.PlotWidget(),
            name='psd',
            title='PSD',
            redraw_f=self._refresh_psd_plot
        )
        plot_psd.plot.plot(pen='b', name='PSD')
        plot_psd.plot.getAxis('bottom').setLabel('Frequency (Hz)')
        plot_psd.plot.getAxis('left').setLabel('Magnitude (dB)')

        plot_spec = self._add_plot(
            plot=pg.PlotWidget(),
            name='spec',
            title='Spectrogram',
            redraw_f=self._refresh_spec_plot
        )
        plot_spec.plot.addItem(pg.ImageItem())
        plot_spec.plot.getAxis('bottom').setLabel('Frequency (Hz)')
        plot_spec.plot.getAxis('left').setLabel('Time (s)')

        for container in self._plots:
            # Default to using the mouse for selecting region instead of pan
            # this can be change by the user by right clicking and selecting
            # the menu item
            container.plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)


    @staticmethod
    def get_iq(plot):
        # This block here should really be part of the underlying plot class
        i_curve = None
        q_curve = None
        for data_item in plot.plotItem.dataItems:
            if data_item.name() == 'I':
                i_curve = data_item
            elif data_item.name() == 'Q':
                q_curve = data_item
            if i_curve is not None and q_curve is not None:
                break
        return (i_curve, q_curve)

    def _add_plot(self, plot, name, title, redraw_f):
        if name in self._plots:
            raise ValueError("Plot with name {} already exists".format(name))

        plot_container = PlottingWidget.PlotContainer(
            name=name,
            plot=plot,
            tab_idx=self._tabs.addTab(plot, title),
            redraw_f=redraw_f
        )
        self._plots.append(plot_container)
        return plot_container

    def get_plot(self, name):
        for plot in self._plots:
            if plot.name == name:
                return plot

    def get_active_plot(self):
        tab_idx = self._tabs.currentIndex()
        for plot in self._plots:
            if plot.tab_idx == tab_idx:
                return plot
        return None

    def refresh_plot(self):
        # type: () -> None
        # Need to look up the correct tab here for now just plot timeseries
        if self._data_source is not None:
            if self._data_source.data is not None:
                for plot in self._plots:
                    plot.redraw(self._data_source)

    def _refresh_time_plot(self, plot, data):
        # type: (DataSource) -> None
        time_range = data.time_range(self._sample_rate)

        # May want to subclass PlotItem to provide access to i and q
        i_curve, q_curve = self.get_iq(plot)
        if i_curve is not None:
            i_curve.setData(time_range, data.data.real)
        if q_curve is not None:
            q_curve.setData(time_range, data.data.imag)

    def _refresh_psd_plot(self, plot, data):
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
        try:
            data_item = plot.plotItem.dataItems[0]
        except IndexError:
            logger.exception('PSD plot could not be found!')
            raise
        data_item.setData(freq_segments, power_d_log)

    def _refresh_spec_plot(self, plot, data):
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

        f_limits = (freq_segments[0], freq_segments[-1])
        t_limits = (time_segments[0], time_segments[-1])
        f_scale = (f_limits[1] - f_limits[0]) / len(freq_segments)
        t_scale = (t_limits[1] - t_limits[0]) / len(time_segments)
        logger.debug("SPEC: fscale: %f, t_scale: %f", f_scale, t_scale)

        pos = (f_limits[0], t_limits[0])

        # Need to reset the transform each time, otherwise the scale/pos
        # transforms will be applied to the existing transform.  Might be able
        # to just supply the transform matrix directly instead of resetting
        # and applying pos and scale in two steps
        try:
            spec_plot = next(plot_item for plot_item in plot.plotItem.items if
                             isinstance(plot_item, pg.ImageItem))
        except StopIteration:
            logger.exception('Spectrogram plot could not be found!')
            raise

        spec_plot.resetTransform()
        spec_plot.setImage(spec)
        spec_plot.translate(*pos)
        spec_plot.scale(f_scale, t_scale)
        spec_plot.getViewBox().setLimits(
            xMin=f_limits[0], xMax=f_limits[1],
            yMin=t_limits[0], yMax=t_limits[1]
        )

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
        t_range /= sample_rate
        return t_range


class MainWindow(QMainWindow):
    """Main window that contains the plot widget as well as the setting"""

    def __init__(self, file=None):
        # type: (str) -> None
        super().__init__()
        self.setWindowTitle('GNURadio Plotting Utility')
        self.setGeometry(0, 0, 1000, 500)
        self._setup_actions()
        self.statusBar()
        self._add_menu()

        self._data_source = DataSource(file)
        # We have not loaded a file yet, so let the file pick the data range
        self._first_file = True
        if file is not None:
            self._first_file = False

        # The tabs for the plots
        self.plot_widget = PlottingWidget(self, self._data_source)

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
        if not file_path:
            # File was not selected
            return
        self._data_source.load_file(file_path, self._first_file)
        self.settings_widget.source_update()
        self.plot_widget.refresh_plot()


@click.command()
@click.option('--file', type=click.Path(exists=True))
@click.option('-v', '--verbose', count=True)
def main(file, verbose):
    # type: (str) -> None
    """Main console entry point"""

    # setup logger
    logging.basicConfig()
    if verbose == 0:
        logger.setLevel(logging.WARNING)
    elif verbose == 1:
        logger.setLevel(logging.INFO)
    else:  # verbose > 1:
        logger.setLevel(logging.DEBUG)

    app = QApplication(sys.argv)

    # Need to prevent the window object form being cleaned up while execution
    # loop is running
    _qt_window = MainWindow(file)
    sys.exit(app.exec_())


if __name__ == '__main__':
    # pylint does not know how to handle parameters that are generated by
    # the decorators PyCQA/pylint/issues/2297
    main()  # pylint: disable=E1120

"""grplot utility.
Provides a QT application for plotting gnuradio data.

Example:
    $ python -m grplot
"""
from typing import (
    Optional, Tuple,
)
import sys
import os
import logging

import pyqtgraph as pg  # type: ignore
import numpy  # type: ignore
from PyQt5 import QtGui
from PyQt5.QtGui import (
    QIcon,
)
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QPushButton, QWidget, QTabWidget, QVBoxLayout,
    QLineEdit, QListWidget, QGridLayout, qApp, QAction,
)

logger = logging.getLogger(__name__)


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

        # Temporary config widgets
        btn = QPushButton('press me')
        text = QLineEdit('enter text')
        list_widget = QListWidget()

        # The tabs for the plots
        self.plot_widget = PlottingeWidget(self)

        # The grid we are working with is 3 rows 2 columns
        layout = QGridLayout()
        layout.addWidget(btn, 0, 0)
        layout.addWidget(text, 1, 0)
        layout.addWidget(list_widget, 2, 0)
        layout.addWidget(self.plot_widget, 0, 1, 3, 2)
        layout.setColumnStretch(1, 1)

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

    def _add_menu(self):
        # type: () -> None
        self._menu_bar = self.menuBar()
        file_menu = self._menu_bar.addMenu('&File')
        file_menu.addAction(self._exit_action)


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

        plot_time = pg.PlotWidget()
        plot_psd = pg.PlotWidget()
        plot_spec = pg.PlotWidget()

        tabs.addTab(plot_time, "Time (iq)")
        tabs.addTab(plot_psd, "PSD")
        tabs.addTab(plot_spec, "Spectrogram")

        # Add tabs to widget
        layout.addWidget(tabs)
        self.setLayout(layout)

        self.data_path = None   # type: Optional[str]


class DataSource(object):
    """Data interface class for plotting"""

    def __init__(self):
        self._data_type = numpy.complex64
        self._source_path = None  # type: Optional[str]
        self.data = numpy.array([], dtype=numpy.complex64)
        self._start = 0  # type: int
        self._end = 0  # type: int

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
        with open(path, 'rb') as fp:
            file_len = os.fstat(fp.fileno()).st_size  # type: int

            new_start, new_end = self._file_range(file_len, reset)

            limits_changed = (new_start, new_end) == (self._start, self._end)
            print(new_start, new_end)
            if limits_changed and not reset:
                # Only log if limits changed unexpectedly
                logger.warning(
                    'Limits out of range [%d, %d] adjusted to [%d, %d]',
                    self._start, self._end, new_start, new_end
                )

            data_size = numpy.dtype(self._data_type).itemsize
            fp.seek(new_start*data_size)
            self._data = numpy.fromfile(fp, self._data_type, new_end-new_start)

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

"""grplot utility.
Provides a QT application for plotting gnuradio data.

Example:
    $ python -m grplot
"""
import sys

import pyqtgraph as pg

from PyQt5 import QtGui
from PyQt5.QtGui import (
    QIcon,
)

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QPushButton, QWidget, QTabWidget, QVBoxLayout,
    QLineEdit, QListWidget, QGridLayout, qApp, QAction,
)


class MainWindow(QMainWindow):
    """Main window that contains the plot widget as well as the setting"""

    def __init__(self):
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
        self._exit_action = QAction('&Exit', self)
        self._exit_action.setShortcut('Ctrl+Q')
        self._exit_action.setStatusTip('Exit application')
        self._exit_action.triggered.connect(qApp.quit)

    def _add_menu(self):
        self._menu_bar = self.menuBar()
        file_menu = self._menu_bar.addMenu('&File')
        file_menu.addAction(self._exit_action)


class PlottingeWidget(QWidget):
    """Container widget class that stores the different plots under
    a tab widget. This also contains the interfaces for controlling
    the data that is being shown"""

    def __init__(self, parent):
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


def main():
    """Main console entry point"""
    app = QApplication(sys.argv)

    # Need to prevent the window object form being cleaned up while execution
    # loop is running
    _qt_window = MainWindow()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

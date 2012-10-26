from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from ... import core

from ...clients.scatter_client import ScatterClient
from ..glue_toolbar import GlueToolbar
from ..mouse_mode import RectangleMode, CircleMode, PolyMode

from ..ui.scatterwidget import Ui_ScatterWidget
from .data_viewer import DataViewer
from .mpl_widget import MplWidget
from ..qtutil import pretty_number

WARN_SLOW = 1000000  # max number of points which render quickly


class ScatterWidget(DataViewer):
    LABEL = "Scatter Plot"

    def __init__(self, data, parent=None):
        super(ScatterWidget, self).__init__(data, parent)
        self.central_widget = MplWidget()
        self.option_widget = QtGui.QWidget()

        self.setCentralWidget(self.central_widget)

        self.ui = Ui_ScatterWidget()
        self.ui.setupUi(self.option_widget)
        self._tweak_geometry()
        self._collection = data

        self.client = ScatterClient(self._collection,
                                    self.central_widget.canvas.fig,
                                    artist_container=self._container)
        self._connect()
        self.unique_fields = set()
        self.make_toolbar()
        self.statusBar().setSizeGripEnabled(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self._setup_limit_editors()

    def _setup_limit_editors(self):
        v = QtGui.QDoubleValidator(None)
        v.setDecimals(4)
        self.ui.xmin.setValidator(v)
        self.ui.xmax.setValidator(v)
        self.ui.ymin.setValidator(v)
        self.ui.ymax.setValidator(v)
        self._update_limit_labels()

    def _tweak_geometry(self):
        self.central_widget.resize(600, 400)
        self.resize(self.central_widget.size())

    def _connect(self):
        ui = self.ui
        cl = self.client

        ui.xLogCheckBox.toggled.connect(cl.set_xlog)
        ui.yLogCheckBox.toggled.connect(cl.set_ylog)
        ui.xFlipCheckBox.toggled.connect(cl.set_xflip)
        ui.yFlipCheckBox.toggled.connect(cl.set_yflip)
        ui.xAxisComboBox.currentIndexChanged.connect(self.update_xatt)
        ui.yAxisComboBox.currentIndexChanged.connect(self.update_yatt)
        ui.swapAxes.clicked.connect(self.swap_axes)
        ui.snapLimits.clicked.connect(cl.snap)
        ui.xmin.editingFinished.connect(self._update_limits)
        ui.xmax.editingFinished.connect(self._update_limits)
        ui.ymin.editingFinished.connect(self._update_limits)
        ui.ymax.editingFinished.connect(self._update_limits)
        self.central_widget.canvas.mpl_connect('draw_event',
                                               self._update_limit_labels)

    @property
    def xmin(self):
        return float(self.ui.xmin.text())

    @xmin.setter
    def xmin(self, value):
        self.ui.xmin.setText(str(value))
        self._update_limits()

    @property
    def xmax(self):
        return float(self.ui.xmin.text())

    @xmax.setter
    def xmax(self, value):
        self.ui.xmax.setText(str(value))
        self._update_limits()

    @property
    def ymin(self):
        return float(self.ui.ymin.text())

    @ymin.setter
    def ymin(self, value):
        self.ui.ymin.setText(str(value))
        self._update_limits()

    @property
    def ymax(self):
        return float(self.ui.ymax.text())

    @ymax.setter
    def ymax(self, value):
        self.ui.ymax.setText(str(value))
        self._update_limits()

    def _update_limits(self, *args):
        xlo = self.ui.xmin.text()
        xhi = self.ui.xmax.text()
        ylo = self.ui.ymin.text()
        yhi = self.ui.ymax.text()
        lims = [xlo, xhi, ylo, yhi]
        for i, l in enumerate(lims):
            try:
                lims[i] = float(l)
            except ValueError:
                lims[i] = 0

        self.client.axes.set_xlim((lims[0], lims[1]))
        self.client.axes.set_ylim((lims[2], lims[3]))
        self.central_widget.canvas.draw()

    def _update_limit_labels(self, *args):
        xlo, xhi = pretty_number(self.client.axes.get_xlim())
        ylo, yhi = pretty_number(self.client.axes.get_ylim())
        self.ui.xmin.setText(xlo)
        self.ui.xmax.setText(xhi)
        self.ui.ymin.setText(ylo)
        self.ui.ymax.setText(yhi)

    def _choose_add_data(self):
        choices = dict([(d.label, d) for d in self._collection])
        dialog = QtGui.QInputDialog()
        choice, isok = dialog.getItem(self, "Data Chooser | Scatter Plot",
                                      "Choose a data set to add",
                                      choices.keys())
        if not isok:
            return
        data = choices[str(choice)]
        self.add_data(data)

    def make_toolbar(self):
        result = GlueToolbar(self.central_widget.canvas, self,
                             name='Scatter Plot')
        for mode in self._mouse_modes():
            result.add_mode(mode)
        self.addToolBar(result)
        return result

    def _mouse_modes(self):
        axes = self.client.axes
        rect = RectangleMode(axes, release_callback=self.apply_roi)
        circ = CircleMode(axes, release_callback=self.apply_roi)
        poly = PolyMode(axes, release_callback=self.apply_roi)
        return [rect, circ, poly]

    def apply_roi(self, mode):
        roi = mode.roi()
        self.client.apply_roi(roi)

    def update_combos(self, layer):
        """ Update combo boxes to incorporate attribute fields in layer"""
        layer_ids = self.client.plottable_attributes(layer, show_hidden=True)
        xcombo = self.ui.xAxisComboBox
        ycombo = self.ui.yAxisComboBox

        for lid in layer_ids:
            if lid not in self.unique_fields:
                xcombo.addItem(lid.label, userData=lid)
                ycombo.addItem(lid.label, userData=lid)
            self.unique_fields.add(lid)

    def add_data(self, data):
        """Add a new data set to the widget

        :rtype: bool
        Returns True if the addition was expected, False otherwise
        """
        if self.client.is_layer_present(data):
            return

        if data.size > WARN_SLOW and not self._confirm_large_data(data):
            return False

        first_layer = self.client.layer_count == 0

        self.client.add_data(data)
        self.update_combos(data)

        if first_layer:  # forces both x and y axes to be rescaled
            self.update_xatt(None)
            self.update_yatt(None)

            self.ui.xAxisComboBox.setCurrentIndex(0)
            if len(data.visible_components) > 1:
                self.ui.yAxisComboBox.setCurrentIndex(1)
            else:
                self.ui.yAxisComboBox.setCurrentIndex(0)

        self._update_window_title()
        return True

    def add_subset(self, subset):
        """Add a subset to the widget

        :rtype: bool:
        Returns True if the addition was accepted, False otherwise
        """
        print 'adding subset'
        if self.client.is_layer_present(subset):
            print 'subset present'
            return

        data = subset.data
        if data.size > WARN_SLOW and not self._confirm_large_data(data):
            return False

        first_layer = self.client.layer_count == 0

        self.client.add_layer(subset)
        self.update_combos(data)

        if first_layer:  # forces both x and y axes to be rescaled
            self.update_xatt(None)
            self.update_yatt(None)

        self.ui.xAxisComboBox.setCurrentIndex(0)
        if len(data.visible_components) > 1:
            self.ui.yAxisComboBox.setCurrentIndex(1)
        else:
            self.ui.yAxisComboBox.setCurrentIndex(0)

        self._update_window_title()
        return True

    def register_to_hub(self, hub):
        super(ScatterWidget, self).register_to_hub(hub)
        self.client.register_to_hub(hub)
        hub.subscribe(self, core.message.DataUpdateMessage,
                      lambda x: self._sync_labels())
        hub.subscribe(self, core.message.ComponentsChangedMessage,
                      lambda x: self.update_combos(x.data))

    def unregister(self, hub):
        hub.unsubscribe_all(self.client)
        hub.unsubscribe_all(self)

    def swap_axes(self):
        xid = self.ui.xAxisComboBox.currentIndex()
        yid = self.ui.yAxisComboBox.currentIndex()
        xlog = self.ui.xLogCheckBox.isChecked()
        ylog = self.ui.yLogCheckBox.isChecked()
        xflip = self.ui.xFlipCheckBox.isChecked()
        yflip = self.ui.yFlipCheckBox.isChecked()

        self.ui.xAxisComboBox.setCurrentIndex(yid)
        self.ui.yAxisComboBox.setCurrentIndex(xid)
        self.ui.xLogCheckBox.setChecked(ylog)
        self.ui.yLogCheckBox.setChecked(xlog)
        self.ui.xFlipCheckBox.setChecked(yflip)
        self.ui.yFlipCheckBox.setChecked(xflip)

    def update_xatt(self, index):
        combo = self.ui.xAxisComboBox
        component_id = combo.itemData(combo.currentIndex())
        assert isinstance(component_id, core.data.ComponentID)
        self.client.set_xdata(component_id)

    def update_yatt(self, index):
        combo = self.ui.yAxisComboBox
        component_id = combo.itemData(combo.currentIndex())
        assert isinstance(component_id, core.data.ComponentID)
        self.client.set_ydata(component_id)

    def _update_window_title(self):
        data = self.client.data
        label = ', '.join([d.label for d in data if
                           self.client.is_visible(d)])
        self.setWindowTitle(label)

    def _sync_labels(self):
        self._update_window_title()

    def __str__(self):
        return "Scatter Widget"

    def options_widget(self):
        return self.option_widget

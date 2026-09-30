"""Shared table copying and a lightweight empty-state overlay."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QTableView

from damage_gui.qt.widgets.workspace import ux


class WorkflowTable(QTableView):
    def __init__(self):
        super().__init__()
        self.zh=False
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.copy_cell_action=QAction(self);self.copy_row_action=QAction(self)
        self.copy_cell_action.triggered.connect(self.copy_cell);self.copy_row_action.triggered.connect(self.copy_row)
        self.addActions([self.copy_cell_action,self.copy_row_action])
        self.empty_label=QLabel(self.viewport());self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setProperty('role','secondary');self.empty_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.retranslate(False)

    def retranslate(self,zh):
        self.zh=zh;self.copy_cell_action.setText(ux('copy',zh));self.copy_row_action.setText(ux('copy_row',zh))
        self.empty_label.setText(ux('empty',zh));self._empty()

    def setModel(self,model):
        super().setModel(model)
        model.modelReset.connect(self._empty);model.rowsInserted.connect(self._empty);self._empty()

    def _empty(self,*_):
        if hasattr(self,'empty_label'):
            self.empty_label.setVisible(self.model() is None or self.model().rowCount()==0)
            self.empty_label.setGeometry(self.viewport().rect())

    def resizeEvent(self,event):super().resizeEvent(event);self._empty()

    def _value(self,index):
        model=self.model();value=model.rows[index.row()].get(model.columns[index.column()])
        return '—' if value is None else str(value)

    def copy_cell(self):
        index=self.currentIndex()
        if index.isValid():QApplication.clipboard().setText(self._value(index))

    def copy_row(self):
        index=self.currentIndex()
        if index.isValid():QApplication.clipboard().setText('\t'.join(self._value(self.model().index(index.row(),column)) for column in range(self.model().columnCount())))

    def keyPressEvent(self,event):
        if event.matches(QKeySequence.Copy):
            rows=sorted({index.row() for index in self.selectedIndexes()})
            if rows:QApplication.clipboard().setText('\n'.join('\t'.join(self._value(self.model().index(row,column)) for column in range(self.model().columnCount())) for row in rows))
            event.accept();return
        super().keyPressEvent(event)

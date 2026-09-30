"""Small shared desktop widgets; no business logic or persistence."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.qt.theme import LG, MD, SM

COPY = {
    'copy': ('复制','Copy'), 'copy_row': ('复制整行','Copy Row'),
    'advanced': ('高级元数据','Advanced Metadata'), 'empty': ('暂无记录','No records'),
    'select': ('选择一行查看详情','Select a row to inspect details'),
    'no_models': ('尚无注册模型','No models registered'),
    'begin': ('训练或加载模型以开始。','Train or load a model to begin.'),
    'exported': ('已导出','Exported'), 'inspect': ('显示检查器','Toggle Inspector'),
    'activity': ('显示任务面板','Toggle Activity Panel'), 'reset': ('重置布局','Reset Layout'),
    'logs': ('显示日志','Toggle Logs'), 'run': ('运行当前操作','Run Current Action'),
    'search': ('搜索当前表格','Search Current Table'),
    'model': ('模型','MODEL'), 'dataset': ('数据集','DATASET'), 'execution': ('执行','EXECUTION'),
    'holdout': ('内置留出验证','BUILT-IN HOLDOUT'), 'provenance': ('来源','PROVENANCE'),
    'training': ('训练','TRAINING'), 'validation': ('验证','VALIDATION'), 'artifact': ('文件','ARTIFACT'),
    'job': ('任务','JOB'), 'input': ('输入','INPUT'), 'result': ('结果','RESULT'),
    'trace': ('追溯','TRACEABILITY'), 'config': ('配置','Configuration'),
    'scope': ('评估范围','Scope'),
    'model_count': ('{count} 个模型 · {active} 个已激活','{count} models · {active} active'),
    'ready': ('准备就绪','Ready'), 'yes': ('是','Yes'), 'no': ('否','No'),
    'samples': ('样本','Samples'), 'page': ('第 {page} 页 · {count} 条记录','Page {page} · {count} records'),
}

def ux(key,zh):return COPY.get(key,(key,key))[0 if zh else 1]


class WorkspaceHeader(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('workspaceHeader')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,SM);layout.setSpacing(4)
        self.title=QLabel();self.title.setProperty('role','page-title')
        self.context=QLabel();self.context.setProperty('role','secondary');self.context.setWordWrap(True)
        from damage_gui.qt.widgets.status_badge import StatusIndicator
        row=QHBoxLayout();row.addWidget(self.title,1)
        self.status=StatusIndicator();self.status.hide();row.addWidget(self.status)
        layout.addLayout(row);layout.addWidget(self.context)


    def set_status(self,state):
        self.status.set_state(state);self.status.show()


class CopyableValue(QLabel):
    def __init__(self,value,*,compact=False,zh=False,parent=None):
        super().__init__(parent)
        self.full_value='—' if value is None else str(value)
        self.compact=compact
        self.display_value=f'{value:.6g}' if isinstance(value,float) else self.full_value
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.setProperty('role','value')
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setToolTip(self.full_value)
        self.setMinimumWidth(0)
        self.setWordWrap(not compact)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.copy_action=QAction(ux('copy',zh),self)
        self.copy_action.triggered.connect(self.copy)
        self.addAction(self.copy_action)
        self._display()

    def copy(self):QApplication.clipboard().setText(self.full_value)

    def _display(self):
        if self.compact:
            preview=Path(self.display_value).name if '/' in self.display_value else self.display_value
            width=min(max(72,self.width()),self.fontMetrics().horizontalAdvance(preview[:16]+'…'+preview[-6:]))
            self.setText(self.fontMetrics().elidedText(preview,Qt.ElideMiddle,width))
        else:self.setText(self.display_value)

    def resizeEvent(self,event):
        self._display();super().resizeEvent(event)


class DetailView(QScrollArea):
    """Sections display facts; raw metadata is opt-in. Plain accessor aids exports."""
    def __init__(self,*,dark=False):
        super().__init__()
        self.dark=dark;self.zh=False;self._plain='';self.sections=[]
        self.setObjectName('detailDark' if dark else 'detailLight')
        self.setWidgetResizable(True);self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content=QWidget();self.content.setObjectName('detailContentDark' if dark else 'detailContentLight')
        self.layout=QVBoxLayout(self.content);self.layout.setContentsMargins(MD,MD,MD,MD);self.layout.setSpacing(LG)
        self.setWidget(self.content)

    def setReadOnly(self,*_):pass
    def setPlaceholderText(self,text):
        if not self._plain:
            self.setPlainText(text)
            self._plain=''
    def clear(self):self.set_sections([])
    def toPlainText(self):return self._plain
    def appendPlainText(self,text):self.set_sections(self.sections+[("",[("",text)])])
    def setPlainText(self,text):self.set_sections([("",[("",text)])])

    def set_sections(self,sections,*,advanced=None,zh=False):
        self.zh=zh;self.sections=sections
        self._plain='\n'.join(str(title)+'\n'+'\n'.join(f'{label}: {value if value is not None else "—"}' if label else str(value) for label,value in rows) for title,rows in sections)
        while self.layout.count():
            item=self.layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for title,rows in sections:
            group=QWidget();col=QVBoxLayout(group);col.setContentsMargins(0,0,0,0);col.setSpacing(SM)
            if title:
                heading=QLabel(title);heading.setProperty('role','section');col.addWidget(heading)
            for label,value in rows:
                row=QHBoxLayout();row.setSpacing(MD)
                if label:
                    key=QLabel(str(label));key.setProperty('role','metric-label');key.setWordWrap(True)
                    key.setFixedWidth(156 if self.dark else 100);row.addWidget(key,0,Qt.AlignTop)
                string='—' if value is None else str(value)
                compact=len(string)>18 and ('sha256:' in string or '/' in string or '\\' in string or (' ' not in string and not isinstance(value,(int,float))))
                widget=CopyableValue(value,compact=compact and bool(label),zh=zh)
                if string in ('SUCCESS','ACTIVE','RUNNING','FAILED','CANCELLED','MISSING','LEGACY','AVAILABLE'):
                    from damage_gui.qt.widgets.status_badge import status_role
                    widget.setProperty('role','status-'+status_role(string))
                row.addWidget(widget,1,Qt.AlignTop);col.addLayout(row)
            self.layout.addWidget(group)
        if advanced is not None:
            toggle=QToolButton();toggle.setText(ux('advanced',zh)+' ▸');toggle.setCheckable(True)
            raw=QPlainTextEdit();raw.setReadOnly(True);raw.setPlainText(json.dumps(advanced,ensure_ascii=False,indent=2,default=str));raw.setMinimumHeight(220);raw.hide()
            toggle.toggled.connect(raw.setVisible)
            self.layout.addWidget(toggle);self.layout.addWidget(raw)
        self.layout.addStretch()


class EmptyState(QWidget):
    def __init__(self,title='',description='',action='',callback=None):
        super().__init__()
        self.layout=QVBoxLayout(self);self.layout.setContentsMargins(LG,LG,LG,LG)
        self.title=QLabel(title);self.title.setProperty('role','page-title')
        self.description=QLabel(description);self.description.setWordWrap(True);self.description.setProperty('role','secondary')
        self.button=QPushButton(action);self.button.setProperty('role','primary');self.button.setVisible(bool(action))
        if callback:self.button.clicked.connect(callback)
        self.layout.addStretch();self.layout.addWidget(self.title);self.layout.addWidget(self.description);self.layout.addWidget(self.button,0,Qt.AlignLeft);self.layout.addStretch()


def scroll_inspector(widget):
    """Keep the inspector identity while making its existing content scrollable."""
    old=widget.layout()
    if old is None:return
    content=QWidget();content.setObjectName('inspectorContent')
    content.setLayout(old)
    outer=QVBoxLayout(widget);outer.setContentsMargins(0,0,0,0)
    scroll=QScrollArea();scroll.setObjectName('inspectorScroll');scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(content);outer.addWidget(scroll)

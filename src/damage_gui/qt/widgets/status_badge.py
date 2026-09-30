"""Small text status indicator; colors come from the theme."""
from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    def __init__(self, text="", role="neutral", parent=None):
        super().__init__(parent)
        self.set_status(text, role)

    def set_status(self, text, role="neutral"):
        role="running" if role=="busy" else role
        self.setText(f"●  {text}" if text else "—")
        self.setProperty("role", f"status-{role}")
        self.style().unpolish(self)
        self.style().polish(self)


def status_role(state):
    return {'SUCCESS':'success','ACTIVE':'success','RUNNING':'running','PENDING':'running',
            'FAILED':'error','CANCELLED':'warning','MISSING':'warning','LEGACY':'neutral','AVAILABLE':'neutral'}.get(state,'neutral')


class StatusIndicator(StatusBadge):
    def set_state(self,state,text=None):
        self.set_status(text or state,status_role(state))

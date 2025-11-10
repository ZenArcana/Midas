from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication


def create_application(argv: Optional[list[str]] = None) -> QApplication:
    """
    Create and configure the global QApplication instance.

    Parameters
    ----------
    argv:
        Optional command line arguments. Defaults to ``sys.argv``.

    Returns
    -------
    QApplication
        A configured Qt application object.
    """

    app = QApplication(argv or sys.argv)

    # Ensure the Qt platform plugin uses XCB on Linux by default unless the
    # user explicitly overrides it.
    app_platform = os.environ.get("QT_QPA_PLATFORM")
    if sys.platform.startswith("linux") and not app_platform:
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    app.setApplicationName("Midas")
    app.setOrganizationName("Midas")
    app.setOrganizationDomain("midas.local")
    return app


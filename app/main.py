from __future__ import annotations

import sys
from typing import NoReturn

from . import create_application
from .ui.main_window import MainWindow


def main() -> NoReturn:
    """
    Entry point for the Midas application.
    """

    app = create_application()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


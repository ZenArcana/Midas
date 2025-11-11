from __future__ import annotations

import sys
from typing import NoReturn

try:
    from . import create_application
    from .ui.main_window import MainWindow
except ImportError:  # pragma: no cover - fallback when executed as a script
    from app import create_application  # type: ignore[no-redef]
    from app.ui.main_window import MainWindow  # type: ignore[no-redef]


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


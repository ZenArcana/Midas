"""
Midas application package.

This module exposes convenience helpers for consumers that integrate with the
application, such as the global QApplication factory.
"""

from .application import create_application

__all__ = ["create_application"]


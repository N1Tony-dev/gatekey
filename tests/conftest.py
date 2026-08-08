import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """QObject signal delivery across real OS threads needs a QCoreApplication
    event loop to dispatch queued connections - without one, signals emitted
    from a background threading.Thread to a receiver that lives on the main
    thread are silently never delivered. Tests that run SequenceWorker.run()
    on a background thread must pump this app's events after joining."""
    app = QApplication.instance() or QApplication([])
    yield app

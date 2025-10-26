from __future__ import annotations

import re

from projects import __version__


def test_version_is_semver() -> None:
    pattern = r"^\d+\.\d+\.\d+$"
    assert re.match(pattern, __version__) is not None

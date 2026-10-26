# SPDX-License-Identifier: 0BSD

import re

import meshchatnext


def test_meshchatnext_version_is_semver_like():
    assert isinstance(meshchatnext.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", meshchatnext.__version__)

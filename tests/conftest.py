#!/usr/bin/env python3
"""
Pytest configuration for api_database_tools tests.
"""

import pytest


def pytest_addoption(parser):
    """Add custom pytest command line option."""
    parser.addoption(
        "--display-results",
        action="store_true",
        default=False,
        help="Display the actual tool output that the model would see"
    )


@pytest.fixture
def display_results(request):
    """Fixture to check if results should be displayed."""
    return request.config.getoption("--display-results")
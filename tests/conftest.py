import pytest

def pytest_addoption(parser):
    parser.addoption("--golden", action="store_true", default=False, help="refresh golden files")

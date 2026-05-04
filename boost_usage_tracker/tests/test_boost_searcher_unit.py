"""Pure-function tests for boost_usage_tracker.boost_searcher."""

from boost_usage_tracker.boost_searcher import (
    extract_boost_includes,
    extract_boost_version_from_content,
)


def test_extract_boost_includes_angle_and_quote():
    src = """
#include <boost/config.hpp>
#include "boost/algorithm/string.hpp"
"""
    headers = extract_boost_includes(src)
    assert "boost/config.hpp" in headers
    assert "boost/algorithm/string.hpp" in headers


def test_extract_boost_includes_empty():
    assert extract_boost_includes("") == []
    assert extract_boost_includes("no includes here") == []


def test_extract_boost_version_from_version_hpp():
    # BOOST_VERSION 106300 -> 1.63.0 style encoding used by decode_boost_version
    content = "#define BOOST_VERSION 106300\n"
    ver = extract_boost_version_from_content(content, "boost/version.hpp")
    assert ver is not None
    assert ver.startswith("1.")


def test_extract_boost_version_from_cmake():
    content = "find_package(Boost 1.82 REQUIRED)\n"
    ver = extract_boost_version_from_content(content, "CMakeLists.txt")
    assert ver is not None


def test_extract_boost_version_from_conan():
    content = 'requires = "boost/1.78.0"\n'
    ver = extract_boost_version_from_content(content, "conanfile.txt")
    assert ver is not None


def test_extract_boost_version_from_vcpkg():
    content = '{"name": "boost", "version": "1.85.0"}'
    ver = extract_boost_version_from_content(content, "vcpkg.json")
    assert ver is not None


def test_extract_boost_version_unknown_filename():
    assert (
        extract_boost_version_from_content("#define BOOST_VERSION 1", "readme.md")
        is None
    )

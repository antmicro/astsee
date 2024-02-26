import os
import shlex
from contextlib import redirect_stdout

import pytest
from testutils import assert_golden

from astsee import generic_cli as astsee

TEST_DIR = os.path.dirname(__file__)
OUT_DIR = TEST_DIR + "/generic_out"
GOLD_DIR = TEST_DIR + "/generic_golden"
IN_DIR = TEST_DIR + "/generic_in"


def run(request, args):
    test_name = request.node.name
    with open(f"{OUT_DIR}/{test_name}", "w+") as out, redirect_stdout(out):
        astsee.main(astsee.parser.parse_args(shlex.split(args)))
    assert_golden(test_name, request.config.option.golden, OUT_DIR, GOLD_DIR)


def test_pprint_with_dict_and_arrs_of_dicts(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json")


def test_pprint_with_dict_and_arrs_of_dicts_html(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json --html")


def test_pprint_with_dict_and_arrs_of_dicts_basic(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json --basic")


def test_diff_with_dict_and_arrs_of_dicts(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json {IN_DIR}/with_dict_and_arrs_of_dicts_b.json")


def test_diff_with_dict_and_arrs_of_dicts_html(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json {IN_DIR}/with_dict_and_arrs_of_dicts_b.json --html")


def test_diff_with_dict_and_arrs_of_dicts_basic(request):
    run(request, f"{IN_DIR}/with_dict_and_arrs_of_dicts_a.json {IN_DIR}/with_dict_and_arrs_of_dicts_b.json --basic")


@pytest.mark.xfail(reason="unimplemented")
def test_pprint_nested_empty_arr(request):
    run(request, f"{IN_DIR}/nested_empty_arr.json")


def test_pprint_nested_empty_arr_basic(request):
    run(request, f"{IN_DIR}/nested_empty_arr.json --basic")


@pytest.mark.xfail(reason="unimplemented")
def test_diff_change_root_type(request):
    run(request, f"{IN_DIR}/empty_arr.json {IN_DIR}/empty_dict.json")


@pytest.mark.xfail(reason="unimplemented")
def test_pprint_mixed_structures(request):
    run(request, f"{IN_DIR}/mixed_structures_a.json")


def test_pprint_mixed_structures_basic(request):
    run(request, f"{IN_DIR}/mixed_structures_a.json --basic")


@pytest.mark.xfail(reason="unimplemented")
def test_diff_mixed_structures(request):
    run(request, f"{IN_DIR}/mixed_structures_a.json {IN_DIR}/mixed_structures_b.json")


def test_diff_mixed_structures_basic(request):
    run(request, f"{IN_DIR}/mixed_structures_a.json {IN_DIR}/mixed_structures_b.json --basic")

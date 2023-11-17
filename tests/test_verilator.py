from astsee import verilator_cli as vastsee
from contextlib import redirect_stdout
import shlex
import os
import pytest
from testutils import assert_golden

TEST_DIR = os.path.dirname(__file__)
OUT_DIR = TEST_DIR + "/verilator_out"
GOLD_DIR = TEST_DIR + "/verilator_golden"
IN_DIR = TEST_DIR + "/verilator_in"

# FIXME: fix output instability of `--html` (caused probably by `set` container that has undefined order)

def run(request, args):
    test_name = request.node.name
    with open(f'{OUT_DIR}/{test_name}', 'w+') as out, redirect_stdout(out):
        vastsee.main(vastsee.parser.parse_args(shlex.split(args)))
    assert_golden(test_name, request.config.option.golden, OUT_DIR, GOLD_DIR)


def test_tree_pprint(request):
    run(request, f'{IN_DIR}/test_a.tree.json')

def test_tree_diff(request):
    run(request, f'{IN_DIR}/test_a.tree.json {IN_DIR}/test_b.tree.json')

def test_tree_diff_filter(request):
    run(request, f'{IN_DIR}/test_a.tree.json {IN_DIR}/test_b.tree.json -d ".editNum"')

def test_tree_pprint_html(request):
    run(request, f'{IN_DIR}/test_a.tree.json --html')

def test_tree_diff_html(request):
    run(request, f'{IN_DIR}/test_a.tree.json {IN_DIR}/test_b.tree.json --html')

def test_pprint_dict_with_one_scalar(request):
    run(request, f'{IN_DIR}/dict_with_one_scalar.json')

@pytest.mark.xfail(reason="unimplemented")
def test_pprint_nested_empty_arr(request):
    run(request, f'{IN_DIR}/nested_empty_arr.json')

@pytest.mark.xfail(reason="unimplemented")
def test_diff_change_root_type(request):
    run(request, f'{IN_DIR}/empty_arr.json {IN_DIR}/empty_dict.json')

import os
import shlex
from contextlib import redirect_stdout

from testutils import assert_golden

from astsee import verilator_cli as vastsee

TEST_DIR = os.path.dirname(__file__)
OUT_DIR = TEST_DIR + "/verilator_out"
GOLD_DIR = TEST_DIR + "/verilator_golden"
IN_DIR = TEST_DIR + "/verilator_in"
os.chdir(IN_DIR)  # html tests rely on relative paths


def run(request, args):
    test_name = request.node.name
    if "_html" in test_name:
        test_name += ".html"
    with open(f"{OUT_DIR}/{test_name}", "w+", encoding="utf-8") as out, redirect_stdout(out):
        vastsee.main(vastsee.parser.parse_args(shlex.split(args)))
    update_golden = request.config.option.golden or "ASTSEE_UPDATE_GOLDEN" in os.environ
    assert_golden(test_name, update_golden, OUT_DIR, GOLD_DIR)


def test_tree_pprint(request):
    run(request, f"{IN_DIR}/test1_a.tree.json")


def test_tree_diff(request):
    run(request, f"{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json")


def test_tree_diff_filter(request):
    run(request, f'{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json -d ".editNum"')


def test_tree_diff_filter2(request):
    run(request, f'{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json -d ".editNum" --del-ptrs')


def test_tree_diff_filter_no_meta(request):
    # empty meta arg disables guessing of meta file path
    run(request, f'{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json --del-ptrs --meta ""')


def test_tree_diff_skip_nodes(request):
    run(request, f"{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json --skip-nodes '.type==\"ASSIGNW\"'")


def test_tree_pprint_html(request):
    run(request, f"{IN_DIR}/test1_a.tree.json --html")


def test_tree_diff_html(request):
    run(request, f"{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json --html")


def test_tree_diff_html_light(request):
    run(request, f"{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json --html --light")


def test_tree_diff_html_filter_no_meta(request):
    # empty meta arg disables guessing of meta file path
    run(request, f'{IN_DIR}/test1_a.tree.json {IN_DIR}/test1_b.tree.json --html --del-ptrs --meta ""')


def test_html_timeline_diff(request):
    run(request, f"--timeline-diff {IN_DIR}/test1_obj_dir/Vtest1.tree.meta.json")


def test_html_timeline_full(request):
    run(request, f"--timeline-full {IN_DIR}/test1_obj_dir/Vtest1.tree.meta.json")


def test_pprint_dict_with_one_scalar(request):
    run(request, f"{IN_DIR}/dict_with_one_scalar.json")


def test_diff_nodelist_replaced_with_scalar(request):
    run(request, f"{IN_DIR}/nodelist_replaced_with_scalar/a.json {IN_DIR}/nodelist_replaced_with_scalar/b.json")


def test_diff_html_nodelist_replaced_with_scalar(request):
    run(request, f"{IN_DIR}/nodelist_replaced_with_scalar/a.json {IN_DIR}/nodelist_replaced_with_scalar/b.json --html")


def test_pprint_nested_empty_arr(request):
    run(request, f"{IN_DIR}/nested_empty_arr.json")


def test_diff_change_root_type(request):
    run(request, f"{IN_DIR}/small_arr.json {IN_DIR}/small_dict.json")

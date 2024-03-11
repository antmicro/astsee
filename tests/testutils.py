import shutil
import sys


def assert_golden2(out_path, golden_path):
    with open(out_path, "r", encoding="utf-8") as f:
        out = list(f)
    with open(golden_path, "r", encoding="utf-8") as f:
        golden = list(f)
    assert out == golden, f"{out_path} != {golden_path}"


def assert_golden(test_name, update_golden, out_dir, golden_dir):
    """Compare output file with golden output file
    If --golden is set, copy output file to golden file"""
    out_path, golden_path = (f"{out_dir}/{test_name}", f"{golden_dir}/{test_name}")
    try:
        assert_golden2(out_path, golden_path)
    finally:
        if update_golden:
            print("Updating golden file: ", golden_path, file=sys.stderr)
            shutil.copyfile(out_path, golden_path)

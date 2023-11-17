import shutil

def assert_golden(test_name, update_golden, out_dir, golden_dir):
    """Compare output file with golden output file
       If --golden is set, copy output file to golden file"""
    out_path, golden_path = (f'{out_dir}/{test_name}', f'{golden_dir}/{test_name}')
    with open(out_path, 'r') as f: out = list(f)
    if update_golden:
        print("Updating golden file: ", golden_path)
        shutil.copyfile(out_path, golden_path)
    try:
        with open(golden_path, 'r') as f: golden = list(f)
    except FileNotFoundError as e:
        raise e
    assert out == golden, f'{out_path} != {golden_path}'

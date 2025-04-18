from os.path import basename
import sys
from astsee import generic_cli, verilator_cli


def usage():
    print(f"usage: {basename(sys.argv[0])} {{json|verilator}} ...")


COMMANDS = {"verilator": verilator_cli.main, "json": generic_cli.main}


def main():
    sys.setrecursionlimit(4000)  # default=1000, we quadruple it in order to allow for deeply nested json
    # argparse has API for subcommands, but at least in our case it is a lot simpler to do it ourselves
    if len(sys.argv) <= 1 or sys.argv[1] not in COMMANDS:
        usage()
    else:
        subcommand = sys.argv.pop(1)
        COMMANDS[subcommand]()


if __name__ == "__main__":
    main()

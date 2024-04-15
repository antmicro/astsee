import argparse
from functools import partial

from astsee import BasicDiffToTerm, DictDiffToHtml, DictDiffToTerm, IntactNode, load_jsons, make_diff

parser = argparse.ArgumentParser(
    description="pretty print json and do optional filtering/diff",
    epilog="""By default (i.e. unless --jq is used), ast_walk(del(empty_ops, <stuff passed to -d>)) is called

examples:
 $ %(prog)s f.json # pretty print in short "inline" mode
 $ %(prog)s old.json new.json # diff in short "inline" mode
 $ %(prog)s old.json new.json --html # diff to html rather than plaintext
 $ %(prog)s old.json new.json --jsonlike # diff in format visually resembling json
""",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)

parser.add_argument(
    "-v", "--verbose", help='print everything (i.e don\'t omit "uninteresting" data)', action="store_false", dest="omit"
)
parser.add_argument("--jq", help="preprocess file(s) with given jq query", default="", dest="jq_query")
parser.add_argument("file", help="file to pretty print (or diff)")
parser.add_argument("newfile", nargs="?", help="optional new version of file (enables diff)", default=None)
parser_group = parser.add_mutually_exclusive_group()
parser_group.add_argument(
    "--html", help="output diff as html rather than plaintext colored with ansi escapes", action="store_true"
)
parser_group.add_argument(
    "--basic", help="output diff in basic, JSON-like format rather than default terse one", action="store_true"
)


def main(args=None):
    if args is None:
        args = parser.parse_args()
    omit_intact = args.omit and args.newfile  # omitting unmodified chunks does not make sense without diff

    if args.html:
        diff_to_str = DictDiffToHtml(omit_intact=omit_intact)
    elif args.basic:
        diff_to_str = BasicDiffToTerm(omit_intact=omit_intact)
    else:
        diff_to_str = DictDiffToTerm(omit_intact=omit_intact)

    load_jsons_ = partial(load_jsons, jq_query=args.jq_query)

    if not args.newfile:  # don't diff, just pretty print
        # passing tree marked as unchanged to colorizer can be abused to just pretty print it
        tree = IntactNode(*load_jsons_([args.file]))
    else:  # both files supplied, diff
        tree = make_diff(*load_jsons_([args.file, args.newfile]))

    print(diff_to_str.diff_to_string(tree), end="")


if __name__ == "__main__":
    main()

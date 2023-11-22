#!/usr/bin/env python3
# pylint: disable=line-too-long,invalid-name,multiple-statements,missing-function-docstring,missing-class-docstring,missing-module-docstring,no-else-return,too-few-public-methods
import argparse
import os
import sys
from functools import partial
import html
from textwrap import dedent
from astsee import make_diff, DictDiffToTerm, DictDiffToHtml, IntactNode, ReplaceDiffNode, stringify, load_jsons


def split_ast_fields(ast, omit_false_flags):
    """split and sort ast fields"""
    implicit = [(k, ast.pop(k))
                for k in ("type", "name", "file", "addr", "editNum")
                if k in ast]
    children = [(k, ast.pop(k)) for k in ("op1", "op2", "op3", "op4")
                if k in ast]

    def should_omit(val):
        if not omit_false_flags: return False
        if isinstance(val, ReplaceDiffNode): return False
        return val.content is False

    explicit = sorted([(k, v) for k, v in ast.items() if not should_omit(v)])
    return implicit, explicit, children


KNOWN_PTR_FIELDS = [
    "abovep", "addr", "blockp", "cellp", "classOrPackageNodep", "classp",
    "cpkgp", "declp", "dtp", "ftaskp", "funcp", "ifacep", "itemp", "labelp",
    "modp", "modVarp", "packagep", "pkgp", "scopep", "sensesp", "subDTypep",
    "taskp", "typedefp", "varp", "varScopep"
]

parser = argparse.ArgumentParser(
    description='pretty print AST json and do optional filtering/diff',
    epilog="""predefined jq functions:
 - ast_walk(f)  apply f to each node (assume that every and only node has op1 field)
 - empty_ops    match all empty op arrays
 - ptrs         match all known pointer fields (like "addr", "varp", "modp" etc.)
 By default (i.e. unless --jq is used), ast_walk(del(empty_ops, <stuff passed to -d>)) is called

examples:
 $ %(prog)s dump.tree.json # pretty print
 $ %(prog)s -d '.file' dump.tree.json # remove "file" fields
 $ %(prog)s -d '.file' 1.tree.json 2.tree.json # remove "file" fields and do diff
 $ %(prog)s -d '.file, .editNum' 1.tree.json # remove "file" and "editNum" fields
 $ %(prog)s -d 'ptrs' 1.tree.json # remove all pointer fields (note lack of dot before func name)

VERILATOR_JQ env-var can be used to supply alternative jq impl (like gojq)
""",
    formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument(
    '-v',
    '--verbose',
    help='print everything (i.e don\'t omit "uninteresting" data)',
    action='store_false',
    dest="omit")
parser_group = parser.add_mutually_exclusive_group()
parser_group.add_argument('-d',
                          '--del-fields',
                          help='delete fields matched by the given jq query',
                          default="",
                          dest="del_list")
parser_group.add_argument('--jq',
                          help='preprocess file(s) with given jq query',
                          default="",
                          dest="jq_query")
parser.add_argument('file', help='file to pretty print (or diff)')
parser.add_argument('newfile',
                    nargs="?",
                    help='optional new version of file (enables diff)',
                    default=None)
parser.add_argument(
    '--html',
    help='output diff as html rather than plaintext colored with ansi escapes',
    action='store_true')


class AstDiffToHtml:
    CSS = dedent("""
    a { color: inherit; }
    :target { /* highlight matched element */
        background-color: gold;
    }
    body {
        display: flex;
        flex-flow: row nowrap;
        height: 100vh;
        margin: 0;
        padding: 0;
        border: 0;
        font-size: 14px;
    }
    .pane {
        height: 100vh;
        border: solid 1px black;
        box-sizing: border-box;
        flex: 0 0 50%;
    }
    .source-pane {
        display: flex;
        flex-flow: column nowrap;

        .tabmenu {
            display: flex;
            flex-flow: row wrap;
        }
        .tabs {
            height: 100%;
            position: relative;
        }
        .tab {
            position: absolute;
            background: white;
            height: 100%;
            width: 100%;
            top: 0;
            left: 0;
        }
        .tab:first-child {
            z-index: 1;
        }
    }
    .y-scrollable {
        overflow-y: scroll;
    }
    """)

    JS = dedent("""\
    var top_idx = 1;
    function showtab(tabname) {
        document.getElementById(tabname).style.zIndex = ++top_idx;
    }""")

    HEAD = ('<head>\n'
            '<meta charset="UTF-8"/>\n'
            '<style>\n'
            '/* Shared CSS */\n'
            f'{DictDiffToHtml.CSS}\n'
            '/* AST specific CSS */'
            f'{CSS}\n'
            '</style>\n'
            '<script>\n'
            f'{JS}\n'
            '</script>\n'
            '</head>\n')

    def __init__(self, omit_intact, split_fields):
        self.srcfiles = set()
        val_handlers = {
            'editNum': (lambda v: html.escape(f'<e{html.escape(str(v))}>')),
            'name': (lambda v: html.escape(f'"{stringify(v, quote_empty=0)}"')),
            "addr": (lambda v: f'<span id="{html.escape(v)}">{html.escape(v)}</span>'),
            'file': self.file_handler,
        }  # yapf: disable
        val_handlers.update({
            k: (lambda v: f'<a href="#{html.escape(v)}">{html.escape(v)}</a>')
            for k in KNOWN_PTR_FIELDS if k != "addr"
        })
        self.diff_to_str_generic = DictDiffToHtml(omit_intact,
                                                        val_handlers,
                                                        split_fields,
                                                        embeddable=True)

    def file_handler(self, val):
        """print file field as link to relevant line and save filename in self.srcfiles for later processing"""
        fname, linenum, _ = val.split(":")
        if fname == "<built-in>": return html.escape(val)  # not a file
        self.srcfiles.add(fname)
        return f'<a href="#{html.escape(fname)}:{html.escape(linenum)}" onclick="showtab(\'{html.escape(fname)}\')">{html.escape(val)}</a>'

    def diff_to_string(self, tree):
        self.srcfiles.clear()
        diff = self.diff_to_str_generic.diff_to_string(tree)
        menu = "\n".join(self.make_btn(fname) for fname in self.srcfiles)
        tabs = "\n".join(self.make_tab(fname) for fname in self.srcfiles)

        return dedent("""\
        <!doctype html>
        <html>
        {}
        <body>

        <div class="pane y-scrollable">
        {}
        </div>

        <div class="pane source-pane">
        <div class="tabmenu">
        {}
        </div>
        <div class="tabs">
        {}
        </div>
        </div>
        </body></html>
        """).format(self.HEAD, diff, menu, tabs)

    def make_btn(self, fname):
        """make button for showing tab"""
        fname = html.escape(fname)
        return f'<button type="button" onclick="showtab(\'{fname}\')">{fname}</button>'

    def make_tab(self, fname):
        """load file into linenumbered tab"""
        fname = html.escape(fname)
        rows = ""
        try:
            with open(fname, encoding='utf-8') as f:
                for i, line in enumerate(f):
                    line = html.escape(line.rstrip())
                    rows += f'<span class="th" id="{fname}:{i+1}">{i+1}</span>{line}\n'
            return f'<div class="tab y-scrollable" id="{fname}"><pre class="code-block">{rows}</pre></div>'
        except FileNotFoundError:
            print(f'WARN: file {fname} not found, skipping', file=sys.stderr)
            return ""


def main(args=None):
    if(args is None): args = parser.parse_args()
    # allow for suplying alternative implementation like gojq
    jq_bin = os.environ.get("VERILATOR_JQ", "jq")

    jq_funcs = """
    # Apply f to each AST node (assume that something is a node if and only if it has the op1 field)
    # TODO: consider using better way of determining wheter something is a node or not
    def ast_walk(f): walk(if type == "object" and has("op1") then f else . end);
    def empty_ops: .op1,.op2,.op3,.op4 | select(length==0);""" + "def ptrs:" + ",".join(
        "." + field for field in KNOWN_PTR_FIELDS) + ";"

    if not args.jq_query:
        if not args.del_list: args.del_list = "empty_ops"
        else: args.del_list += ",empty_ops"
        args.jq_query = f"ast_walk(del({args.del_list}))"

    split_fields = partial(split_ast_fields, omit_false_flags=args.omit)
    omit_intact = args.omit and args.newfile  # ommiting unmodified chunks does not make sense without diff

    if args.html:
        diff_to_str = AstDiffToHtml(omit_intact, split_fields)
    else:
        val_handlers = {
            'editNum': (lambda v: f'<{stringify(v)}>'),
            'name': (lambda v: f'"{stringify(v, quote_empty=0)}"'),
        }
        diff_to_str = DictDiffToTerm(omit_intact, val_handlers, split_fields)

    load_jsons_ = partial(load_jsons,
                          jq_bin=jq_bin,
                          jq_funcs=jq_funcs,
                          jq_query=args.jq_query)

    if not args.newfile:  # don't diff, just pretty print
        # passing tree marked as unchanged to colorizer can be abused to just pretty print it
        tree = IntactNode(*load_jsons_([args.file]))
    else:  # both files suplied, diff
        tree = make_diff(*load_jsons_([args.file, args.newfile]))

    print(diff_to_str.diff_to_string(tree), end="")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# pylint: disable=line-too-long,invalid-name,multiple-statements,missing-function-docstring,missing-class-docstring,missing-module-docstring,no-else-return,too-few-public-methods
import argparse
import glob
import html
import json
import logging as log
import os
import webbrowser
from functools import partial
from tempfile import NamedTemporaryFile

import pygments
import pygments.formatters
import pygments.lexers
import pygments.styles

from astsee import (
    DictDiffToHtml,
    DictDiffToTerm,
    IntactNode,
    ReplaceDiffNode,
    is_children,
    load_jsons,
    make_diff,
    stringify,
)


def split_ast_fields(ast, omit_false_flags):
    """split and sort ast fields"""
    implicit = [(k, ast.pop(k)) for k in ("type", "name", "loc", "addr", "editNum") if k in ast]
    children = [(k, v) for k, v in ast.items() if is_children(v)]
    for k, v in children:
        del ast[k]

    def should_omit(val):
        if not omit_false_flags:
            return False
        if isinstance(val, ReplaceDiffNode):
            return False
        return val.content is False

    explicit = sorted([(k, v) for k, v in ast.items() if not should_omit(v)])
    return implicit, explicit, children


parser = argparse.ArgumentParser(
    description="pretty print AST json and do optional filtering/diff",
    epilog="""predefined jq functions:
 - ast_walk(f)  apply f to each node (assume that every and only node has op1 field)
 - empty_ops    match all empty op arrays
 - ptrs         match all known pointer fields (like "addr", "varp", "modp" etc.)
 By default (i.e. unless --jq is used), ast_walk(select(<stuff passed to --skip-nodes> | not) | del(empty_ops, <stuff passed to -d>)) is called

examples:
 $ %(prog)s dump.tree.json # pretty print
 $ %(prog)s -d '.file' dump.tree.json # remove "file" fields
 $ %(prog)s -d '.file' 1.tree.json 2.tree.json # remove "file" fields and do diff
 $ %(prog)s -d '.file, .editNum' 1.tree.json # remove "file" and "editNum" fields
 $ %(prog)s -d 'ptrs' 1.tree.json # remove all pointer fields (note lack of dot before func name)
 $ %(prog)s --skip-nodes '.type=="ASSIGNW"' 1.tree.json # remove nodes of type ASSIGNW
 $ %(prog)s --skip-nodes '.loc | split(",") | .[0]=="d"' 1.tree.json # remove nodes located in file with id "d"

VERILATOR_JQ env-var can be used to supply alternative jq impl (like gojq)
""",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)

parser.add_argument(
    "-v", "--verbose", help='print everything (i.e don\'t omit "uninteresting" data)', action="store_false", dest="omit"
)
parser_group = parser.add_mutually_exclusive_group()
parser_group.add_argument(
    "-d", "--del-fields", help="delete fields matched by the given jq query", default="", dest="del_list"
)
parser_group.add_argument(
    "--skip-nodes", help="Skip AST nodes matched by the given jq query", default="false", dest="skip_nodes"
)
parser_group.add_argument("--jq", help="preprocess file(s) with given jq query", default="", dest="jq_query")
parser.add_argument(
    "--meta",
    help="path to .tree.meta.json used for resolving ids and identifying ptr fields.\n"
    "If not given, astsee will try to deduce it from .tree.json path.\n"
    "If not found, ids won't be resolved, and hardcoded list will be used for fields identification",
    default=None,
    dest="meta",
)
parser.add_argument("file", help=".tree.json file to pretty print (or diff)")
parser.add_argument("newfile", nargs="?", help="optional new version of .tree.json file (enables diff)", default=None)
parser.add_argument(
    "--html", help="output diff as html rather than plaintext colored with ansi escapes", action="store_true"
)
parser.add_argument(
    "--htmlb",
    help="like --html, but the generated file is opened in a web browser",
    action="store_true",
    dest="html_browser",
)
parser.add_argument(
    "--loglevel",
    default="warning",
    choices=["critical", "error", "warning", "info", "debug"],
    help="log level. default=warning",
)


class AstDiffToHtml:
    def __init__(self, omit_intact, split_fields, meta):
        self.meta = meta
        self.srcfiles = set()
        val_handlers = {
            'editNum': (lambda v: html.escape(f'<e{html.escape(str(v))}>')),
            'name': (lambda v: html.escape(f'"{stringify(v, quote_empty=0)}"')),
            "addr": (lambda v: f'<span id="{html.escape(v)}">{html.escape(v)}</span>'),
            'loc': self.loc_handler,
        }  # yapf: disable
        val_handlers.update(
            {
                k: (lambda v: f'<a href="#{html.escape(v)}">{html.escape(v)}</a>')
                for k in meta["ptrFieldNames"]
                if k != "addr"
            }
        )
        self.diff_to_str_generic = DictDiffToHtml(omit_intact, val_handlers, split_fields, embeddable=True)
        extern_css = DictDiffToHtml.CSS + self.make_highlighter().get_style_defs(".code-block")
        with open(f"{os.path.dirname(__file__)}/rich_view.js", encoding="utf-8") as f:
            js = f.read()
        globals_ = {"make_tab": self.make_tab, "extern_css": extern_css, "js": js}
        self.template = self.diff_to_str_generic.make_html_tmpl("rich_view.html.jinja", globals_)

    def resolve_path(self, file):
        # Try to find symbolic/relative (prefered) or absolute path of file.
        # Returns tuple (found, path)
        #
        # NOTE: supsectible to TOCTOU, but it should not be a problem for us
        sym_path = file["filename"]
        abs_path = file["realpath"]

        if sym_path in ("<built-in>", "<command-line>"):  # not a file
            return False, sym_path
        if os.path.exists(sym_path):
            return True, sym_path
        if os.path.exists(abs_path):
            return True, abs_path

        if sym_path == "<verilated_std>" and "VERILATOR_ROOT" in os.environ:
            log.warning("'%s' not found, falling back to $VERILATOR_ROOT/include/verilated_std.sv", abs_path)
            abs_path = os.path.join(os.environ["VERILATOR_ROOT"], "include", "verilated_std.sv")

        log.warning("'%s' nor '%s' not found, skipping. cwd: {os.getcwd()}", sym_path, abs_path)
        return False, sym_path

    def loc_handler(self, loc):
        """print location field as link to relevant line and save filename in self.srcfiles for later processing"""
        id_, begin, end = loc.split(",")
        (begin_row, begin_col), (end_row, end_col) = begin.split(":"), end.split(":")

        if id_ not in self.meta["files"]:
            return f"{html.escape(id_)}:{html.escape(begin_row)}"

        found, path = self.resolve_path(self.meta["files"][id_])
        if not found:
            if path in ("<built-in>", "<command-line>"):
                return html.escape(path)  # not a file. row/col location is also irrevelant
            else:
                return html.escape(loc)
        else:
            self.srcfiles.add(path)
            onclick = f"return selectFileFragment('{html.escape(path)}',{int(begin_row)},{int(begin_col)},{int(end_row)},{int(end_col)})"
            short_loc = f"{html.escape(path)}-{html.escape(begin_row)}"
            return f'<a href="#{short_loc}" onclick="{onclick}">{short_loc}</a>'

    def diff_to_string(self, tree):
        self.srcfiles.clear()
        diff = self.diff_to_str_generic.diff_to_string(tree)
        return self.template.render({"diff": diff, "srcfiles": sorted(self.srcfiles)})

    def make_highlighter(self, lineanchor_id=None):
        # arbitrarily chosen style that does not override background (for consistency with non-pygments content)
        style = pygments.styles.get_style_by_name("xcode")
        return pygments.formatters.HtmlFormatter(  # pylint: disable=maybe-no-member
            linenos="inline", lineanchors=lineanchor_id, style=style, cssclass="code-block"
        )

    def make_tab(self, fname):
        """load file into linenumbered tab"""
        rows = ""
        try:
            with open(fname, encoding="utf-8") as f:
                verilog_lex = pygments.lexers.VerilogLexer()  # pylint: disable=maybe-no-member
                rows = pygments.highlight(f.read(), verilog_lex, self.make_highlighter(fname))
            return f'<div class="tab y-scrollable" id="{fname}">{rows}</div>'
        except FileNotFoundError:
            log.warning("file '%s' not found, skipping", fname)
            return ""


def load_meta(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        log.warning("meta file not found. Some features may not work")
        return {"files": {}, "pointers": {}, "ptrFieldNames": [
        # when meta not found, we default to hardcoded (likely outdated) list of ptr fields
        "abovep", "addr", "blockp", "cellp", "classOrPackageNodep", "classp",
        "cpkgp", "declp", "dtp", "ftaskp", "funcp", "ifacep", "itemp", "labelp",
        "modp", "modVarp", "packagep", "pkgp", "scopep", "sensesp", "subDTypep",
        "taskp", "typedefp", "varp", "varScopep"
        ]}  # fmt: skip


def guess_meta_path(args):
    def match(name):
        # Yeah, this is a bit overengineered scheme, but it should work
        # even if you have multiple meta files in same dir
        common = os.path.commonprefix([os.path.abspath(name), os.path.abspath(args.file)])
        if not common:
            return False

        return os.path.abspath(name) in (
            common + ".tree.meta.json",  # Vtest1_990_final.tree.json -> Vtest1.tree.meta.json
            common + "meta.json",  # test1.tree.json -> test1.tree.meta.json
        )

    pattern = os.path.join(glob.escape(os.path.dirname(args.file)), "*.tree.meta.json")
    matches = [x for x in glob.glob(pattern) if match(x)]
    if len(matches) == 1:  # only unambiguous match
        args.meta = matches[0]
        log.info("'%s' guessed as meta file", args.meta)
    else:
        args.meta = ""


def plaintext_loc_handler(loc, meta):
    id_, begin, _ = loc.split(",")
    line = begin.split(":")[0]
    if id_ in meta["files"]:
        return f'{meta["files"][id_]["filename"]}:{line}'
    else:
        return f"{id_}:{line}"


def main(args=None):
    # pylint: disable=too-many-branches
    if args is None:
        args = parser.parse_args()
    log.basicConfig(level=args.loglevel.upper())
    if args.meta is None:
        guess_meta_path(args)

    meta = load_meta(args.meta)
    # allow for suplying alternative implementation like gojq
    jq_bin = os.environ.get("VERILATOR_JQ", "jq")

    jq_funcs = """
    # Apply f to each AST node (assume that something is a node if and only if it is object)
    def ast_walk(f): walk(if type == "object" then f else . end);
    def empty_ops: .[] | select(type=="array" and length==0);"""
    if meta["ptrFieldNames"]:
        jq_funcs += "def ptrs:" + ",".join("." + field for field in meta["ptrFieldNames"]) + ";"
    else:
        jq_funcs += "def ptrs: empty;"

    if not args.jq_query:
        if not args.del_list:
            args.del_list = "empty_ops"
        else:
            args.del_list += ",empty_ops"
        args.jq_query = f"ast_walk(select({args.skip_nodes} | not) | del({args.del_list}))"

    split_fields = partial(split_ast_fields, omit_false_flags=args.omit)
    omit_intact = args.omit and args.newfile  # ommiting unmodified chunks does not make sense without diff

    if args.html or args.html_browser:
        diff_to_str = AstDiffToHtml(omit_intact, split_fields, meta)
    else:
        loc_handler = partial(plaintext_loc_handler, meta=meta)
        val_handlers = {
            "editNum": (lambda v: f"<{stringify(v)}>"),
            "name": (lambda v: f'"{stringify(v, quote_empty=0)}"'),
            "loc": loc_handler,
        }
        diff_to_str = DictDiffToTerm(omit_intact, val_handlers, split_fields)

    load_jsons_ = partial(load_jsons, jq_bin=jq_bin, jq_funcs=jq_funcs, jq_query=args.jq_query)

    if not args.newfile:  # don't diff, just pretty print
        # passing tree marked as unchanged to colorizer can be abused to just pretty print it
        tree = IntactNode(*load_jsons_([args.file]))
    else:  # both files suplied, diff
        tree = make_diff(*load_jsons_([args.file, args.newfile]))

    if args.html_browser:
        with NamedTemporaryFile("w", delete=False, suffix=".html") as out:
            out.write(diff_to_str.diff_to_string(tree))
            webbrowser.open(f"file://{out.name}")
    else:
        print(diff_to_str.diff_to_string(tree), end="")


if __name__ == "__main__":
    main()

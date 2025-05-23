#!/usr/bin/env python3
# pylint: disable=line-too-long,invalid-name,multiple-statements,missing-function-docstring,missing-class-docstring,missing-module-docstring,no-else-return,too-few-public-methods
import argparse
import filecmp
import glob
import html
import json
import logging as log
import os
import re
import sys
import webbrowser
from functools import partial
from tempfile import NamedTemporaryFile
from itertools import chain, zip_longest

import multiprocess
import pygments
import pygments.formatters
import pygments.lexers
import pygments.styles

from astsee import (
    DictDiffToHtml,
    DictDiffToTerm,
    IntactNode,
    ReplaceDiffNode,
    load_jsons,
    make_diff,
    stringify,
    COLOR_GREEN,
    COLOR_RED,
)


def split_ast_fields(ast, omit_false_flags):
    """split and sort AST fields"""
    implicit = [(k, ast.pop(k)) for k in ("type", "name", "loc", "addr", "editNum") if k in ast]
    children = [(k, v) for k, v in ast.items() if v.is_container()]
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
    prog="astsee verilator",
    description="pretty print AST json and do optional filtering/diff",
    epilog="""predefined jq functions:
 - ast_walk(f)  apply f to each node (assume that every and only node has op1 field)

examples:
 $ %(prog)s dump.tree.json # pretty print
 $ %(prog)s -d '.file' dump.tree.json # remove "file" fields
 $ %(prog)s -d '.file' 1.tree.json 2.tree.json # remove "file" fields and do diff
 $ %(prog)s -d '.file, .editNum' 1.tree.json # remove "file" and "editNum" fields
 $ %(prog)s --del-ptrs 1.tree.json # remove all pointer fields
 $ %(prog)s --skip-nodes '.type=="ASSIGNW"' 1.tree.json # remove nodes of type ASSIGNW
 $ %(prog)s --skip-nodes '.loc | split(",") | .[0]=="d"' 1.tree.json # remove nodes located in file with id "d"

VERILATOR_JQ env-var can be used to supply alternative jq impl (like gojq)
""",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)

parser.add_argument(
    "-v", "--verbose", help='print everything (i.e don\'t omit "uninteresting" data)', action="store_false", dest="omit"
)
parser.add_argument(
    "-d", "--del-fields", help="delete fields matched by the given jq query", default="", dest="del_list"
)
parser.add_argument(
    "--del-ptrs", help="delete fields that seem to hold pointer", default="", action="store_true", dest="del_ptrs"
)
parser.add_argument("--skip-nodes", help="Skip AST nodes matched by the given jq query", default="", dest="skip_nodes")
parser.add_argument(
    "--jq",
    help="preprocess file(s) with given jq query. Incompatible with -d and --skip-nodes",
    default="",
    dest="jq_query",
)
parser.add_argument(
    "--meta",
    help="path to .tree.meta.json used for resolving ids and identifying ptr fields.\n"
    "If not given, astsee will try to deduce it from .tree.json path.\n"
    "If not found, ids won't be resolved, and hardcoded list will be used for fields identification",
    default=None,
    dest="meta",
)
timeline_args = parser.add_argument_group(
    title="--timeline-(diff|pprint|full)",
    description='Produce html that includes "timeline" of consecutive stages.\n'
    "`file` param should point to .tree.meta.json, that is expected to be inside obj_dir alongside stage-numbered .tree.json files.\n"
    "Stages that didn't introduce any change are skipped from timeline. By default implies --html but you can still specify --htmlb",
)
timeline_args.add_argument(
    "--timeline-diff", help="Include diffs of consecutive stages", action="store_true", dest="timeline_diff"
)
timeline_args.add_argument(
    "--timeline-pprint", help="Pretty print each stage", action="store_true", dest="timeline_pprint"
)
timeline_args.add_argument(
    "--timeline-full",
    help="Combination of --timeline-diff --timeline-pprint",
    action="store_true",
    dest="timeline_full",
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
parser.add_argument("--light", help="Use light theme. Applicable with --html(b)", action="store_true")
parser.add_argument(
    "--loglevel",
    default="warning",
    choices=["critical", "error", "warning", "info", "debug"],
    help="log level. default=warning",
)


class HtmlHighlighter(pygments.formatters.HtmlFormatter):  # pylint: disable=maybe-no-member
    def __init__(self, dark, backref_lines=None, fname=None):
        if dark:
            # style = pygments.styles.get_style_by_name("github-dark")
            style = pygments.styles.get_style_by_name("gruvbox-dark")
        else:
            style = pygments.styles.get_style_by_name("xcode")
        super().__init__(style=style, cssclass="code-block")
        self.backref_lines = backref_lines
        self.fname = fname

    def wrap(self, source):
        i = 0
        source = tuple(source)
        lines_cnt = sum((is_source_line for is_source_line, _ in source))
        idx_width = len(str(lines_cnt))

        yield (
            0,
            f'<div class="code-block" style="text-indent: calc({idx_width}ch + 2*{DictDiffToHtml.LINENOS_SIDE_PADDING}) hanging each-line;"><pre>',
        )
        for is_source_line, line in source:
            if is_source_line:
                i += 1
                line_id = f"{html.escape(self.fname)}-{i}"
                span = f'<span class="linenos" style="width:{idx_width}ch;">{i}</span>'
                if i in self.backref_lines:
                    onclick = f"return gotoClassInAst('back-{line_id}')"
                    line_prefix = f'<a id="{line_id}" class="backref" href="#" onclick="{onclick}">{span}</a>'
                else:
                    line_prefix = f'<a id="{line_id}">{span}</a>'
                line = f"{line_prefix}{line}"
            yield is_source_line, line
        yield 0, "</pre></div>"


class AstDiffToHtml:
    def __init__(self, meta, dark=True, **generic_diff_to_html_kwargs):
        """
        Args other than `meta` and `dark` are handled by DictDiffToHtml.
        Args that are known to be safely overridable: `omit_intact` and `split_fields`.
        Other ones may or may not work, as AstDiffToHtml sets some of them itself.
        """
        self.meta = meta
        self.dark = dark
        self.referenced_lines = {}  # filename : set_of_referenced_lines
        val_handlers = {
            'editNum': (lambda v: html.escape(f'<e{html.escape(str(v))}>')),
            'name': (lambda v: "<b>" + html.escape(f'"{stringify(v, quote_empty=0)}"') + "</b>"),
            "addr": (lambda v: f'<span class="{html.escape(v)}">{html.escape(v)}</span>'),
            'loc': self.loc_handler,
        }  # yapf: disable
        val_handlers.update({k: self.format_ptr_link for k in meta["ptrFieldNames"] if k != "addr"})
        if dark:
            colors = {COLOR_RED: "#e74a3c", COLOR_GREEN: "#00af91"}
        else:
            colors = None
        self.diff_to_str_generic = DictDiffToHtml(
            embeddable=True, colors=colors, val_handlers=val_handlers, **generic_diff_to_html_kwargs
        )
        extern_css = DictDiffToHtml.CSS + HtmlHighlighter(dark).get_style_defs(".code-block")
        with open(f"{os.path.dirname(__file__)}/rich_view.js", encoding="utf-8") as f:
            js = f.read()
        self.template_globals = {"make_tab": self.make_tab, "extern_css": extern_css, "js": js, "dark": dark}

    def format_ptr_link(self, ptr):
        if ptr == "UNLINKED":
            return "UNLINKED"
        else:
            onclick = f"return gotoClassInAst('{html.escape(ptr)}')"
            return f'<a href="#{html.escape(ptr)}" onclick="{onclick}">{html.escape(ptr)}</a>'

    def loc_handler(self, loc):
        """print location field as link to relevant line and save filename in self.srcfiles for later processing"""
        id_, begin_row, begin_col, end_row, end_col = re.split("[:,]", loc)

        if id_ not in self.meta["files"]:
            return f"{html.escape(id_)}:{html.escape(begin_row)}"

        file = self.meta["files"][id_]
        realpath = file["realpath"]
        link_loc = f"{html.escape(realpath)}-{html.escape(begin_row)}"
        display_loc = f"{file['truncated_html']}-{html.escape(begin_row)}"

        if not file["found"]:
            return display_loc
        else:
            self.referenced_lines.setdefault(realpath, set())
            self.referenced_lines[realpath].add(int(begin_row))
            onclick = f"return selectFileFragment('{html.escape(realpath)}',{int(begin_row)},{int(begin_col)},{int(end_row)},{int(end_col)})"
            return f'<a class="back-{link_loc}" href="#{link_loc}" onclick="{onclick}">{display_loc}</a>'

    def timeline(self, load_jsons_, outfile, do_diff, do_pprint):  # pylint: disable=too-many-locals
        """
        generate timeline from `meta["timelineFiles"]` (have to be populated beforehand by `gather_timeline_files()`)

        `load_jsons_()` should be a function that takes array of filenames, and returns parsed jsons

        `do_diff` and `do_pprint` are configuration bools. If both are true, then diffs and pprints are interleaved
        """

        def do_partial_diff(old_path, new_path):
            referenced_lines, diff = self.diff_to_string_partial(make_diff(*load_jsons_([old_path, new_path])))
            return f"{old_path} -> {new_path}", referenced_lines, diff

        def do_partial_pprint(path):
            self.diff_to_str_generic.omit_intact = False  # omitting unmodified chunks does not make sense without diff
            # NOTE: since this method runs in child process we can modify fields without "global" consequences
            referenced_lines, diff = self.diff_to_string_partial(IntactNode(*load_jsons_([path])))
            return path, referenced_lines, diff

        def merge(dest, src):
            """merge referenced lines (dicts of sets)"""
            for k, v in src.items():
                if k not in dest:
                    dest[k] = v
                else:
                    dest[k].update(v)

        with multiprocess.Pool() as pool:  # pylint: disable=maybe-no-member
            # SIDENOTE: For some reason `multiprocess` and `multiprocessing` insist on serializing and passing
            # everything used in child processes (code and input) through IPC. I get that it might make sense
            # in case of windows that does not have fork(), but it seems like unnecessary work
            diffs = {}
            pprints = {}
            if do_diff:
                for name, referenced_lines, ast in pool.starmap(do_partial_diff, pairwise(self.meta["timelineFiles"])):
                    merge(self.referenced_lines, referenced_lines)
                    diffs[name] = ast
            if do_pprint:
                for name, referenced_lines, ast in pool.map(do_partial_pprint, self.meta["timelineFiles"]):
                    merge(self.referenced_lines, referenced_lines)
                    pprints[name] = ast

        # interleave diffs and pprints
        asts = [x for x in chain.from_iterable(zip_longest(pprints.items(), diffs.items())) if x is not None]

        template = self.diff_to_str_generic.make_html_tmpl("rich_view.html.jinja", self.template_globals)
        template.stream({"asts": asts, "srcfiles": sorted(self.referenced_lines)}).dump(outfile)

    def diff_to_string(self, tree):
        self.referenced_lines.clear()
        diff = self.diff_to_str_generic.diff_to_string(tree)
        template = self.diff_to_str_generic.make_html_tmpl("rich_view.html.jinja", self.template_globals)
        return template.render({"asts": [("placeholder_name", diff)], "srcfiles": sorted(self.referenced_lines)})

    def diff_to_file(self, tree, outfile):
        self.referenced_lines.clear()
        diff = self.diff_to_str_generic.diff_to_string(tree)
        template = self.diff_to_str_generic.make_html_tmpl("rich_view.html.jinja", self.template_globals)
        template.stream({"asts": [("placeholder_name", diff)], "srcfiles": sorted(self.referenced_lines)}).dump(outfile)

    def diff_to_string_partial(self, tree):
        """stringize AST, but instead of feeeding it directly into template,
        return it alongside list of referenced files/lines"""
        self.referenced_lines.clear()
        diff = self.diff_to_str_generic.diff_to_string(tree)
        return self.referenced_lines, diff

    def make_tab(self, fname):
        """load file into line-numbered tab"""
        rows = ""
        try:
            with open(fname, encoding="utf-8") as f:
                verilog_lex = pygments.lexers.VerilogLexer()  # pylint: disable=maybe-no-member
                rows = pygments.highlight(
                    f.read(), verilog_lex, HtmlHighlighter(self.dark, self.referenced_lines[fname], fname)
                )
            return f'<div class="tab y-scrollable" id="{fname}">{rows}</div>'
        except FileNotFoundError:
            log.warning("file '%s' not found, skipping", fname)
            return ""


def pairwise(iterable):
    # polyfill for itertools.pairwise() (avaible since 3.10)
    # pairwise('ABCDEFG') → AB BC CD DE EF FG
    iterator = iter(iterable)
    a = next(iterator, None)
    for b in iterator:
        yield a, b
        a = b


def truncate_path(path, abs_prefix, rel_prefix):
    if abs_prefix and path.startswith(abs_prefix):
        truncated = "/..." + path[len(abs_prefix) :]
        truncated_html = f'<span title="{html.escape(path)}">{html.escape(truncated)}</span>'
    elif rel_prefix and path.startswith(rel_prefix):
        truncated = "..." + path[len(rel_prefix) :]
        truncated_html = f'<span title="{html.escape(path)}">{html.escape(truncated)}</span>'
    else:
        truncated = path
        truncated_html = html.escape(truncated)

    return truncated, truncated_html


def resolve_path(file):
    # Try to find symbolic/relative (preferred) or absolute path of file.
    # Returns tuple (found, path)
    #
    # NOTE: susceptible to TOCTOU, but it should not be a problem for us
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


def preprocess_paths(meta):
    abs_paths = []
    rel_paths = []
    for f in meta["files"].values():
        f["found"], f["realpath"] = resolve_path(f)
        if f["filename"] in ("<built-in>", "<command-line>", "<verilated_std>"):
            # we skip <built-in> and <command-line> as they are not real files
            # we skip <verilated_std> from calculating common prefix, as it is very likely that
            # it is stored in different place (so it would artificially shorten trucated fragment)
            continue
        if os.path.isabs(f["realpath"]):
            abs_paths.append(f["realpath"])
        else:
            rel_paths.append(f["realpath"])

    abs_path_prefix = os.path.commonpath(abs_paths) if len(abs_paths) > 1 else ""
    rel_path_prefix = os.path.commonpath(rel_paths) if len(rel_paths) > 1 else ""

    for file in meta["files"].values():
        file["truncated"], file["truncated_html"] = truncate_path(file["realpath"], abs_path_prefix, rel_path_prefix)


def load_meta(path, timeline=False):
    try:
        with open(path, encoding="utf-8") as file:
            meta = json.load(file)
            preprocess_paths(meta)
            if timeline:
                meta["timelineFiles"] = gather_timeline_files(os.path.dirname(path))
            return meta

    except FileNotFoundError:
        log.warning("meta file not found. Some features may not work")
        return {"files": {}, "pointers": {}, "ptrFieldNames": [
        # when meta not found, we default to hardcoded (likely outdated) list of pointer fields
        "abovep", "addr", "blockp", "cellp", "classOrPackageNodep", "classp",
        "cpkgp", "declp", "dtp", "ftaskp", "funcp", "ifacep", "itemp", "labelp",
        "modp", "modVarp", "packagep", "pkgp", "scopep", "sensesp", "subDTypep",
        "taskp", "typedefp", "varp", "varScopep"
        ]}  # fmt: skip


def guess_meta_path(args):
    def match(name):
        # Yeah, this is a bit overengineered, but it should work
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
        return f"{meta['files'][id_]['truncated']}:{line}"
    else:
        return f"{id_}:{line}"


def preprocess_args(args):
    log.basicConfig(level=args.loglevel.upper())

    if args.timeline_full:
        args.timeline_pprint = True
        args.timeline_diff = True

    if args.timeline_pprint or args.timeline_diff:
        args.html = True
        args.meta = args.file
        if args.meta is None:
            log.critical("meta file must be provided for timeline to work")
            sys.exit(1)
    elif args.meta is None:
        guess_meta_path(args)

    if args.jq_query and (args.skip_nodes or args.del_list):
        log.critical("--jq is incompatible with --del-fields and --skip-nodes")
        sys.exit(1)
    elif args.skip_nodes and args.del_list:
        args.jq_query = f"ast_walk(select({args.skip_nodes} | not) | del({args.del_list}))"
    elif args.skip_nodes:
        args.jq_query = f"ast_walk(select({args.skip_nodes} | not))"
    elif args.del_list:
        args.jq_query = f"ast_walk(del({args.del_list}))"


def gather_timeline_files(obj_dir):
    """Go through numbered .tree.json files in obj_dir, and return them in alphanumeric order"""
    paths = []
    predecessor_path = None
    # requiring occurence of three consecutive digits is used as heuristic to skip non-stage dumps
    # (e.g. output of --json-only) that would mess dump ordering
    pattern = os.path.join(glob.escape(obj_dir), "*[0-9][0-9][0-9]*.tree.json")
    for path in sorted(glob.glob(pattern)):
        path = os.path.relpath(path)
        if predecessor_path and filecmp.cmp(predecessor_path, path, shallow=False):
            log.info("skipping dump with unchanged content: %s", path)
        else:
            paths.append(path)
            predecessor_path = path
    return paths


def main(args=None):
    if args is None:
        args = parser.parse_args()
    preprocess_args(args)
    meta = load_meta(args.meta, args.timeline_diff or args.timeline_pprint)

    # allow for supplying an alternative implementation like gojq
    jq_bin = os.environ.get("VERILATOR_JQ", "jq")

    jq_funcs = """
    # Apply f to each AST node (assume that something is a node if and only if it is object)
    def ast_walk(f):
        # 0-ary recursive helper, weird but common jq opt
        # (see https://github.com/jqlang/jq/blob/ed8f7154f4e3e0a8b01e6778de2633aabbb623f8/src/builtin.jq#L249)
        def w:
            if type == "array"
            then select(. != []) | map(f | map_values(w))
            else .
            end
            ;
        f|map_values(w);
    """

    load_jsons_ = partial(load_jsons, jq_bin=jq_bin, jq_funcs=jq_funcs, jq_query=args.jq_query)

    if args.del_ptrs:

        def should_skip_field(k, v):
            return v == [] or (k in meta["ptrFieldNames"] and isinstance(v, str))

        def json_object_hook(obj):
            return {k: v for k, v in obj.items() if not should_skip_field(k, v)}
    else:

        def json_object_hook(obj):
            return {k: v for k, v in obj.items() if v != []}

    load_jsons_ = partial(
        load_jsons, jq_bin=jq_bin, jq_funcs=jq_funcs, jq_query=args.jq_query, object_hook=json_object_hook
    )

    split_fields = partial(split_ast_fields, omit_false_flags=args.omit)
    omit_intact = args.omit and (
        args.newfile or args.timeline_diff or args.timeline_full
    )  # omitting unmodified chunks does not make sense without diff

    if args.html or args.html_browser:
        diff_to_str = AstDiffToHtml(omit_intact=omit_intact, split_fields=split_fields, meta=meta, dark=not args.light)
    else:
        loc_handler = partial(plaintext_loc_handler, meta=meta)
        val_handlers = {
            "editNum": (lambda v: f"<{stringify(v)}>"),
            "name": (lambda v: f'"{stringify(v, quote_empty=0)}"'),
            "loc": loc_handler,
        }
        diff_to_str = DictDiffToTerm(omit_intact=omit_intact, val_handlers=val_handlers, split_fields=split_fields)

    def diff_to_file(outfile):
        if args.timeline_diff or args.timeline_pprint:
            diff_to_str.timeline(load_jsons_, outfile, args.timeline_diff, args.timeline_pprint)
        elif not args.newfile:  # don't diff, just pretty print
            # passing tree marked as unchanged to colorizer can be abused to just pretty print it
            diff_to_str.diff_to_file(IntactNode(*load_jsons_([args.file])), outfile)
        else:  # both files supplied, diff
            diff_to_str.diff_to_file(make_diff(*load_jsons_([args.file, args.newfile])), outfile)

    if args.html_browser:
        with NamedTemporaryFile("w", delete=False, suffix=".html") as outfile:
            diff_to_file(outfile)
            if args.html_browser:
                webbrowser.open(f"file://{outfile.name}")
    else:
        diff_to_file(sys.stdout)


if __name__ == "__main__":
    main()

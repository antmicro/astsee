# pylint: disable=line-too-long,invalid-name,multiple-statements,missing-function-docstring,missing-class-docstring,missing-module-docstring,no-else-return,too-few-public-methods
import html
import json
import os
import subprocess
import sys
import textwrap

import jinja2

COLOR_RESET = "\u001b[39m"
COLOR_RED = "\u001b[31m"
COLOR_GREEN = "\u001b[32m"
COLOR_YELLOW = "\u001b[33m"


def is_scalar(obj):
    return not isinstance(obj, (list, dict))


def stringify(x, quote_empty=True):
    """Return x as string with "special chars" escaped. For sake of readability we return empty strings as '""' rather than '' (unless quote_empty==False)"""
    x = str(x).encode("unicode_escape").decode("utf-8")
    if x or not quote_empty:
        return x
    else:
        return '""'


class DiffNode:
    def __init__(self, content):
        self.content = content

    def dict_it(self, omit=0):
        """iterator that propagates diff markers and optionally omits uninteresting nodes"""
        for key, subnode in self.content.items():
            subnode = self.propagate(subnode)
            if omit and subnode.shouldOmit():
                if isinstance(subnode.content, list):
                    subnode = OmittedNode(len(subnode.content))
                else:
                    subnode = OmittedNode(1)
            yield key, subnode

    def list_it(self, omit=0):
        """iterator that propagates diff markers and optionally omits uninteresting nodes"""
        if omit:
            yield from self.list_omit_it()
        else:
            for subnode in self.content:
                yield self.propagate(subnode)

    def list_omit_it(self):
        omit_count = 0
        for elem in self.list_it():
            if elem.shouldOmit():
                omit_count += 1
            else:
                if omit_count:
                    yield OmittedNode(omit_count)
                    omit_count = 0
                yield elem
        if omit_count:
            yield OmittedNode(omit_count)

    def shouldOmit(self):
        return False

    def propagate(self, child):
        if not isinstance(child, DiffNode):
            return IntactNode(child)
        return child

    def is_container(self):
        """return true if looks like container"""
        return isinstance(self.content, (list, dict))

    def color(self):
        return COLOR_RESET

    def symbol(self):
        return " "

    def colsym(self):
        return self.color() + self.symbol()


class ParentOfModified(DiffNode):
    """Node that has modified descendants"""

    def is_container(self):
        return True  # parent is obviously container


class IntactNode(DiffNode):
    """Node that is common between old and new JSONs"""

    def shouldOmit(self):
        return not is_scalar(self.content)


class OmittedNode(IntactNode):
    """Intact node that has been omitted. As adjacent nodes are often collapsed together,
    count of omissions is stored in self.content"""

    def is_container(self):
        return True  # only containers are turned into OmittedNode


class DelDiffNode(DiffNode):
    def color(self):
        return COLOR_RED

    def propagate(self, child):
        return DelDiffNode(child)

    def symbol(self):
        return "-"


class AddDiffNode(DiffNode):
    def color(self):
        return COLOR_GREEN

    def propagate(self, child):
        return AddDiffNode(child)

    def symbol(self):
        return "+"


class ReplaceDiffNode(DiffNode):
    def __init__(self, old, new):
        # pylint: disable=super-init-not-called
        self.old = DelDiffNode(old)
        self.new = AddDiffNode(new)

    def is_container(self):
        return isinstance(self.old.content, (list, dict)) or isinstance(self.new.content, (list, dict))

    def color(self):
        return COLOR_YELLOW

    def symbol(self):
        return "~"


def make_diff_dict(old, new):
    intact = True
    for k, old_val in old.items():
        if k not in new:
            old[k] = DelDiffNode(old_val)
        else:
            old[k] = make_diff(old_val, new[k])
        intact &= isinstance(old[k], IntactNode)

    for k, new_val in new.items():
        if k not in old:
            old[k] = AddDiffNode(new_val)
            intact = False

    if intact:
        return IntactNode(old)
    else:
        return ParentOfModified(old)


def make_diff_list(old, new):
    intact = len(old) == len(new)
    for i in range(min(len(old), len(new))):
        old[i] = make_diff(old[i], new[i])
        intact &= isinstance(old[i], IntactNode)

    for i in range(len(new), len(old)):
        old[i] = DelDiffNode(old[i])
    for i in range(len(old), len(new)):
        old.append(AddDiffNode(new[i]))

    if intact:
        return IntactNode(old)
    else:
        return ParentOfModified(old)


def make_diff(old, new):
    """Diff @old and @new and return result as DiffNode.
    Note: this function do not tag every node, so separate propagation of tags is needed (see DiffNode.list_it() and DiffNode.dict_it())
    """
    if isinstance(old, type(new)):
        if isinstance(old, dict):
            return make_diff_dict(old, new)
        elif isinstance(old, list):
            return make_diff_list(old, new)
        elif old != new:
            return ReplaceDiffNode(old, new)
        else:
            return IntactNode(old)
    else:  # we allow for basic types only, so if types differ, values differ too
        return ReplaceDiffNode(old, new)


class BasicDiffToTerm:
    """class for producing pretty representation of diff, colored with ANSI escapes.
    Input may contain lists, dicts and scalars (can be potentially extended in future to user defined types)
    Output looks like simplified JSON with each record on its own line (for more condensed output see DictDiffToTerm/DictDiffToHtml).
    """

    def __init__(self, omit_intact):
        self.omit_intact = (
            omit_intact  # represent chunks of unchanged non-scalars (dicts/arrays) as "... * <count of omissions>"
        )

    def diff_to_string(self, diff):
        if isinstance(diff, IntactNode):
            # remove unnecessary ANSI escape flood from unmodified tree
            return self._diff_to_string(diff).replace(COLOR_RESET, "")
        else:
            return f"{self._diff_to_string(diff)}{COLOR_RESET}"

    def diff_to_file(self, diff, outfile):
        outfile.write(self.diff_to_string(diff))

    def _diff_to_string(self, diff, indent="", key_prefix=""):
        """Return pretty representation of JSON diff."""
        if isinstance(diff, ReplaceDiffNode):
            if is_scalar(diff.old.content) and is_scalar(diff.new.content):
                return f"{diff.colsym()}{COLOR_RESET}{indent}{key_prefix}{diff.old.color()}{stringify(diff.old.content)}{COLOR_RESET} -> {diff.new.color()}{stringify(diff.new.content)}\n"
            else:
                return f"{self._diff_to_string(diff.old, indent, key_prefix)}{self._diff_to_string(diff.new, indent, key_prefix)}"
        subindent = f"{indent}  "

        if isinstance(diff, OmittedNode):
            s = f"... * {str(diff.content)}"
        elif isinstance(diff.content, list):
            s = "".join(self._diff_to_string(subnode, subindent, "") for subnode in diff.list_it(self.omit_intact))
            s = f"[\n{s}{diff.colsym()}{indent}]"
        elif isinstance(diff.content, dict):
            s = "".join(
                self._diff_to_string(subnode, subindent, subkey + ": ")
                for subkey, subnode in diff.dict_it(self.omit_intact)
            )
            s = f"{{\n{s}{diff.colsym()}{indent}}}"
        else:
            s = stringify(diff.content)
        return f"{diff.colsym()}{indent}{key_prefix}{s}\n"


def default_split_fields(diff):
    implicit = []
    explicit = sorted([(k, v) for k, v in diff.items() if not v.is_container()])
    children = sorted([(k, v) for k, v in diff.items() if v.is_container()])
    return implicit, explicit, children


class DictDiff:
    """Base class for DictDiffToTerm and DictDiffToHtml
    Output format looks like this (example is a bit simplified):
    implicit_fields explicit_fields
     children_name:
       implicit_fields explicit_fields
       ...

    Explicit fields are printed as key:value, whereas implicit ones are printed by
    value only (useful for common "positional" fields).

    By default:
     - no field is considered "implicit"
     - every list is assumed to hold dicts (or nothing)
     - every list or dict is assumed to be child

    Behaviour can be customized by supplying custom split_fields() method and val_handlers dict

    Addition and Deletion is signaled with colors, and replacement is: `deletion_of_old->addition_of_new`
    Color handling shall be implemented in _colorize() method of child class
    """

    def __init__(self, omit_intact=False, val_handlers=None, split_fields=None):
        """
        - if omit_intact is set then chunks of unchanged non-scalars are emitted as "... * <count of omissions>".
        - val_handlers, if specified, should be dict that maps key into custom value formatter: {key: value_formatter(value_content)}.
          As of now, only implicit and explicit fields can be handled this way.
        - split_fields(), if specified, should be function that turns dict into tuple: (implicit, explicit, children) where
          each group is list of (key,value) pairs. See default_split_fields for example.
        """
        self.omit_intact = (
            omit_intact  # represent chunks of unchanged non-scalars (dicts/arrays) as "... * <count of omissions>"
        )
        self.val_handlers = {} if val_handlers is None else val_handlers
        self.split_fields = default_split_fields if split_fields is None else split_fields

    def _colorize(self, color, text):
        raise NotImplementedError

    def diff_to_string(self, diff):
        return self._diff_to_string(diff, "")

    def diff_to_file(self, diff, outfile):
        outfile.write(self.diff_to_string(diff))

    def _diff_to_string(self, diff, indent):
        if isinstance(diff, OmittedNode):
            return f'{indent}{self._colorize(diff.color(), f"... * {diff.content}")}\n'
        if isinstance(diff, ReplaceDiffNode):
            return self._diff_to_string(diff.old, indent) + self._diff_to_string(diff.new, indent)
        if isinstance(diff.content, list):
            s = ""
            for child in diff.list_it(self.omit_intact):
                s += self._diff_to_string(child, f"{indent} ")
            return s
        if isinstance(diff.content, dict):
            diff = dict(diff.dict_it(self.omit_intact))
            implicit, explicit, children = self.split_fields(diff)
            implicit = " ".join((self._output_implicit(k, v) for k, v in implicit))
            explicit = ", ".join(self._output_explicit(k, v) for k, v in explicit)
            children = "".join((self._output_children(k, v, indent) for k, v in children))
            sep = " " if explicit and implicit else ""
            return f"{indent}{implicit}{sep}{explicit}\n{children}"
        return f"{indent}{self._colorize(diff.color(), diff.content)}\n"

    def _output_val(self, key, val, default_handler=stringify):
        return self.val_handlers.get(key, default_handler)(val.content)

    def _output_implicit(self, key, val):
        if isinstance(val, ReplaceDiffNode):
            return f"{self._output_implicit(key, val.old)}->{self._output_implicit(key, val.new)}"
        return self._colorize(val.color(), self._output_val(key, val))

    def _output_explicit(self, key, val, replacement=False):
        # don't output key twice
        prefix = "" if replacement else f"{stringify(key)}:"
        if isinstance(val, ReplaceDiffNode):
            return f"{prefix}{self._output_explicit(key, val.old, True)}->{self._output_explicit(key, val.new, True)}"
        return self._colorize(val.color(), prefix + self._output_val(key, val))

    def _output_children(self, key, children, indent):
        if isinstance(children, ReplaceDiffNode):
            return (
                f"{self._output_children(key, children.old, indent)}{self._output_children(key, children.new, indent)}"
            )

        if children.is_container():
            return f'{indent} {self._colorize(children.color(), f"{key}:")}\n{self._diff_to_string(children, f"{indent}  ")}'
        else:  # Scalar may get classified as children (e.g when array was replaced with string)
            return f'{indent} {self._colorize(children.color(), f"{key}:")} {self._diff_to_string(children, "")}'


class DictDiffToTerm(DictDiff):
    """class for producing pretty representation of dict diff, colored with ANSI escapes. For more thorough description see DictDiff"""

    def _colorize(self, color, text):
        if color == COLOR_RESET:
            return text
        else:
            return f"{color}{text}{COLOR_RESET}"


class DictDiffToHtml(DictDiff):
    """like DictDiffToTerm but output is formatted as line-numbered html rather than ANSI escapes text
    By default result is standalone html page with styles.
    If `embeddable` flag set, then diff_to_string() returns only "code-block" without CSS and other boilerplate.
    `colors` dict can be used to set COLOR_RED and COLOR_GREEN to custom hues
    Other consturctor args are passed verbatim to DictDiff

    Format of code-table:
    <div class="code-block">
    <pre>
    <div class="chunk> # lines are split into smaller chunks for performance reasons
    <span class="th">1</span>first line
    <span class="th">2</span>second line
    ...lines...
    </div>
    <div class="chunk">
    ...lines...
    </pre>
    </div>
    """

    LINENOS_SIDE_PADDING = "5px"

    CSS = textwrap.dedent(
        """\
    .code-block {
        .linenos {
            padding: 0 %s 0 %s;
        }
        .chunk {
          content-visibility: auto;
        }
        pre {
            margin: 0 0;
            white-space: pre-wrap;
            overflow-wrap: break-word;
        }
    }
    """
        % (LINENOS_SIDE_PADDING, LINENOS_SIDE_PADDING)
    )

    CHUNK_SIZE = 1000

    # pylint: disable=too-many-arguments
    def __init__(self, embeddable=False, colors=None, **dict_diff_kwargs):
        super().__init__(**dict_diff_kwargs)
        self.embeddable = embeddable
        if colors is None:
            self.colors = {COLOR_RED: "red", COLOR_GREEN: "green"}
        else:
            self.colors = colors
        self.template_globals = {"embeddable": embeddable, "CSS": self.CSS, "CHUNK_SIZE": self.CHUNK_SIZE}

    def _colorize(self, color, text):
        if color == COLOR_RESET:
            return text
        return f'<span style="color:{self.colors[color]};">{text}</span>'

    def escape(self, x):
        return html.escape(stringify(x))

    def _output_val(self, key, val, default_handler=None):
        if default_handler is None:
            default_handler = self.escape
        return self.val_handlers.get(key, default_handler)(val.content)

    def diff_to_string(self, diff):
        template = self.make_html_tmpl("basic_view.html.jinja", self.template_globals)
        return template.render({"diff": self._diff_to_string(diff, "").splitlines()})

    def diff_to_file(self, diff, outfile):
        template = self.make_html_tmpl("basic_view.html.jinja", self.template_globals)
        template.stream({"diff": self._diff_to_string(diff, "").splitlines()}).dump(outfile)

    def make_html_tmpl(self, name, globals_=None):
        """Load jinja template from astsee dir, enable autoescape and set globals_"""
        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(__file__)), autoescape=True
        ).get_template(name, globals=globals_)


def load_jsons(files, jq_query, jq_bin="jq", jq_funcs="", object_hook=None):
    """Load JSONs and return them as array.
    If jq_query is not empty, files are preprocessed with jq
    For sake of performance, preprocessing is done in parallel"""
    # pylint: disable=consider-using-with

    if not jq_query:
        return [json.load(open(f, encoding="utf-8"), object_hook=object_hook) for f in files]

    procs = []
    for file in files:
        cmd = [jq_bin, jq_funcs + " " + jq_query, file]
        try:
            procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE))
        except FileNotFoundError:
            print(f"{jq_bin} executable not found (make sure it is installed)", file=sys.stderr)
            sys.exit(1)

    out = []
    for proc in procs:
        stdout, _ = proc.communicate()
        if proc.returncode:
            print(f"{jq_bin} exited with non-zero code", file=sys.stderr)
            sys.exit(proc.returncode)
        out.append(json.loads(stdout, object_hook=object_hook))

    return out

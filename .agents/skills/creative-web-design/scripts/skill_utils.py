"""Small, deliberately bounded Skill frontmatter reader (Python 3.9+).

This is not a general YAML parser. Supported syntax: a leading --- header;
top-level string scalars (plain, JSON-style double quoted, YAML single quoted,
or |/> blocks); and a flat `metadata` mapping of those scalars. Unsupported
collections, anchors, tags, duplicate keys, implicit non-string YAML scalars,
and deeper mappings fail explicitly. Body Markdown is not parsed.
"""

import json
import re
from pathlib import Path

MAX_ENTRY_BYTES = 1024 * 1024
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_IMPLICIT = re.compile(
    r"^(?:null|~|true|false|yes|no|on|off|[-+]?\.(?:inf|nan)|"
    r"[-+]?(?:0[xob][0-9a-f_]+|[0-9][0-9_]*(?:\.[0-9_]*)?(?:e[-+]?[0-9]+)?|"
    r"\.[0-9_]+(?:e[-+]?[0-9]+)?|[0-9]+(?::[0-9]+)+)|"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt ].*)?)$", re.IGNORECASE
)


def _plain_comment(value):
    # A '#' starts a YAML comment only after whitespace (or at the beginning).
    return re.split(r"(?:^|\s)#", value, maxsplit=1)[0].rstrip()


def _scalar(value, line_number):
    value = value.strip()
    if value.startswith('"'):
        decoder = json.JSONDecoder()
        try:
            result, end = decoder.raw_decode(value)
        except (ValueError, json.JSONDecodeError):
            raise ValueError("Invalid double-quoted scalar on line %d" % line_number)
        suffix = value[end:]
        trailing = suffix.strip()
        if not isinstance(result, str) or (trailing and (not suffix[0].isspace() or not trailing.startswith("#"))):
            raise ValueError("Invalid quoted scalar suffix on line %d" % line_number)
        return result
    if value.startswith("'"):
        index, chars = 1, []
        while index < len(value):
            if value[index] == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    chars.append("'")
                    index += 2
                    continue
                suffix = value[index + 1:]
                trailing = suffix.strip()
                if trailing and (not suffix[0].isspace() or not trailing.startswith("#")):
                    raise ValueError("Invalid quoted scalar suffix on line %d" % line_number)
                return "".join(chars)
            chars.append(value[index])
            index += 1
        raise ValueError("Unclosed single-quoted scalar on line %d" % line_number)
    value = _plain_comment(value)
    if not value:
        raise ValueError("Empty scalar on line %d" % line_number)
    if value[0] in "[{&*!?@`" or value == "-" or value.startswith("- ") or re.search(r":(?:\s|$)", value):
        raise ValueError("Unsupported YAML scalar syntax on line %d" % line_number)
    if _IMPLICIT.fullmatch(value):
        raise ValueError("Non-string or ambiguous YAML scalar on line %d; quote it" % line_number)
    return value


def _block(lines, index, parent_indent, marker):
    values = []
    indentation = None
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            values.append("")
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= parent_indent:
            break
        if indentation is None:
            indentation = indent
        if indent < indentation:
            raise ValueError("Inconsistent block indentation on line %d" % (index + 2))
        values.append(line[indentation:])
        index += 1
    if indentation is None:
        raise ValueError("Empty YAML block scalar")
    if marker.startswith("|"):
        result = "\n".join(values)
    else:
        # Fold consecutive nonempty lines; retain paragraph breaks.
        result = ""
        for position, value in enumerate(values):
            if position:
                result += " " if value and values[position - 1] else "\n"
            result += value
    if marker.endswith("-"):
        result = result.rstrip("\n")
    elif not marker.endswith("+"):
        result = result.rstrip("\n") + "\n"
    return result, index


def parse_frontmatter(text):
    """Return the supported frontmatter mapping, or raise ValueError."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must begin with a genuine --- frontmatter header")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("Frontmatter closing --- is missing")
    header, output, index, current_map = lines[1:end], {}, 0, None
    while index < len(header):
        line = header[index]
        line_number = index + 2
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[:len(line) - len(line.lstrip())]:
            raise ValueError("Tab indentation is unsupported on line %d" % line_number)
        indent = len(line) - len(line.lstrip(" "))
        content = line[indent:]
        if ":" not in content:
            raise ValueError("Expected YAML key:value on line %d" % line_number)
        key, raw = content.split(":", 1)
        if not _KEY.fullmatch(key):
            raise ValueError("Invalid YAML key on line %d" % line_number)
        if indent:
            if current_map != "metadata" or indent != 2:
                raise ValueError("Only a flat, two-space metadata mapping is supported")
            destination = output["metadata"]
        else:
            current_map, destination = None, output
        if key in destination:
            raise ValueError("Duplicate frontmatter key: %s" % key)
        plain = _plain_comment(raw.strip())
        if not indent and key == "metadata" and not plain:
            output[key], current_map = {}, "metadata"
            continue
        if plain in ("|", "|-", "|+", ">", ">-", ">+"):
            value, index = _block(header, index, indent, plain)
        else:
            value = _scalar(raw, line_number)
        destination[key] = value
    for required in ("name", "description"):
        if not isinstance(output.get(required), str) or not output[required].strip():
            raise ValueError("Required frontmatter field %s must be a nonempty string" % required)
    if "\n" in output["name"] or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", output["name"]):
        raise ValueError("Skill name must be a lowercase hyphenated identifier")
    if len(output["name"]) > 64:
        raise ValueError("Skill name exceeds 64 characters")
    if "metadata" in output and not isinstance(output["metadata"], dict):
        raise ValueError("metadata must use the supported flat mapping syntax")
    return output


def read_frontmatter(path: Path) -> dict:
    """Read one bounded UTF-8 SKILL.md; malformed/unsupported YAML raises ValueError."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_ENTRY_BYTES + 1)
    if len(raw) > MAX_ENTRY_BYTES:
        raise ValueError("SKILL.md exceeds the 1 MiB safety bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("SKILL.md is not valid UTF-8")
    return parse_frontmatter(text)

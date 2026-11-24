"""YAML parsing and JSON Schema validation shared by the catalog and frontmatter loaders.

Every hand-edited file in a library passes through this module before any typed record is built
from it, so a loader can trust the shape of what it receives.
"""

import json
from collections.abc import Hashable
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
"""Directory that holds the JSON Schema files, at the root of the tooling repository."""

type SchemaName = Literal["resource", "catalog", "chapter", "topic"]

_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"
_MERGE_TAG = "tag:yaml.org,2002:merge"


class LoadError(Exception):
    """A library file could not be read, parsed, or validated.

    Attributes:
        path: The file that failed.
        message: What is wrong, without the file name.
        json_path: JSON path of the failing value, such as ``$.license.spdx``. It is ``None``
            when the failure is not tied to one value, as with unreadable or malformed files.
    """

    def __init__(self, path: Path, message: str, json_path: str | None = None) -> None:
        """Build the error and its one-line description."""
        self.path = path
        self.message = message
        self.json_path = json_path
        location = f"{path}: {json_path}" if json_path else str(path)
        super().__init__(f"{location}: {message}")


class _Loader(yaml.SafeLoader):
    """Safe YAML loader that keeps dates as strings and refuses a repeated key or a merge key."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        """Build a mapping, and fail when one of its keys could hold two values.

        PyYAML keeps the last of two equal keys and says nothing. A record decides a license
        status, so a second ``third_party_rights`` line below the first would change the
        decision while a reader of the file sees both. A merge key does the same thing by
        another route, because the mapping it merges gives a key a value that an explicit
        line overrides. No file of the library needs one, so a merge key is refused.

        Args:
            node: The mapping node.
            deep: Whether to build the values at once, as PyYAML defines it.

        Raises:
            yaml.constructor.ConstructorError: A key of the mapping is repeated, or the
                mapping holds a merge key.
        """
        seen: set[Hashable] = set()
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found a merge key, and a file of this library takes none",
                    key_node.start_mark,
                )
            key = self.construct_object(key_node, deep=True)
            # The base class reports a key that cannot be hashed.
            if not isinstance(key, Hashable):
                continue
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found the key {key!r} a second time",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


# PyYAML turns an unquoted 2026-11-20 into a date object, which no JSON Schema string type
# accepts. Records keep dates as ISO strings, so the timestamp resolver is left out.
_Loader.yaml_implicit_resolvers = {
    first_character: [(tag, pattern) for tag, pattern in resolvers if tag != _TIMESTAMP_TAG]
    for first_character, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@cache
def _validator(schema: SchemaName) -> Draft202012Validator:
    text = (SCHEMA_DIR / f"{schema}.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(text))


def read_text(path: Path) -> str:
    """Read a library file as UTF-8 text.

    Raises:
        LoadError: The file is missing, unreadable, or not valid UTF-8.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise LoadError(path, "The file does not exist.") from error
    except (OSError, UnicodeDecodeError) as error:
        raise LoadError(path, f"The file could not be read: {error}") from error


def parse_yaml(text: str, path: Path) -> object:
    """Parse YAML text with the safe loader.

    Unquoted dates stay strings. Everything else follows PyYAML's safe rules, so a bare ``yes``
    or ``no`` still becomes a boolean.

    Args:
        text: The YAML text.
        path: The file the text came from, used only in the error.

    Raises:
        LoadError: The text is not well-formed YAML.
    """
    try:
        # _Loader subclasses SafeLoader, so this constructs plain data only.
        return yaml.load(text, Loader=_Loader)
    except yaml.YAMLError as error:
        detail = " ".join(str(error).split())
        raise LoadError(path, f"The YAML is malformed: {detail}") from error


def validate(document: object, schema: SchemaName, path: Path) -> dict[str, Any]:
    """Validate a parsed document against one of the library's schemas.

    Args:
        document: The parsed YAML value.
        schema: Which schema to apply.
        path: The file the document came from, used only in the error.

    Returns:
        The same document, now known to be a mapping that satisfies the schema.

    Raises:
        LoadError: The document breaks the schema. The error carries the JSON path of the
            failing value. When several values fail, the one nearest the top is reported.
    """
    if not isinstance(document, dict):
        raise LoadError(path, "The document must be a YAML mapping.", json_path="$")
    error = best_match(_validator(schema).iter_errors(document))
    if error is not None:
        raise LoadError(path, error.message, json_path=error.json_path)
    return document


def load_yaml_file(path: Path, schema: SchemaName) -> dict[str, Any]:
    """Read, parse, and validate a YAML file.

    Raises:
        LoadError: The file cannot be read, is not well-formed YAML, or breaks the schema.
    """
    return validate(parse_yaml(read_text(path), path), schema, path)

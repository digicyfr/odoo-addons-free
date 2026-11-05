"""Small, offline checks of Odoo's stored XML architecture.

This is deliberately a structural comparison, not a renderer or crawler.
"""

import hashlib
import re

from lxml import etree


MAX_ARCH_BYTES = 256 * 1024
MAX_NODES = 2500
MIN_TEXT_LENGTH = 12
SKIP_TAGS = {"script", "style", "code", "pre", "svg", "textarea", "noscript"}
GENERIC_ALT = {"image", "photo", "picture", "img", "obraz", "zdjęcie", "grafika"}
EXPRESSION_MARKERS = ("{{", "}}", "${")
UNSAFE_XML = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
SPACE = re.compile(r"\s+")


class AnalysisLimit(Exception):
    """An XML input exceeded a documented safety bound."""


class UnsafeArchitecture(Exception):
    """An XML input could require entity or DTD interpretation."""


def normalize(value):
    return SPACE.sub(" ", value or "").strip()


def digest(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def parse_arch(arch):
    raw = (arch or "").encode("utf-8")
    if len(raw) > MAX_ARCH_BYTES:
        raise AnalysisLimit("architecture byte limit")
    if UNSAFE_XML.search(raw):
        raise UnsafeArchitecture("DOCTYPE or ENTITY declaration")
    root = etree.fromstring(
        raw, parser=etree.XMLParser(resolve_entities=False, load_dtd=False,
                                    no_network=True, huge_tree=False)
    )
    if sum(1 for _ in root.iter()) > MAX_NODES:
        raise AnalysisLimit("architecture node limit")
    return root


def _dynamic(node):
    if not isinstance(node.tag, str):
        return True
    if etree.QName(node).localname.lower() in SKIP_TAGS:
        return True
    for name, value in node.attrib.items():
        if name == "t-translation" and value == "off":
            return True
        if name == "t-call" and value == "website.layout":
            continue
        if name.startswith("t-") and name not in ("t-name", "t-translation"):
            return True
    return False


def static_units(root):
    """Map stable XML paths to text, skipping QWeb-controlled subtrees."""
    tree = root.getroottree()
    units = {}

    def walk(node, dynamic_parent=False):
        dynamic = dynamic_parent or _dynamic(node)
        if not dynamic:
            path = tree.getpath(node)
            value = normalize(node.text)
            if value and not any(marker in value for marker in EXPRESSION_MARKERS):
                units[path + "/text()"] = value
        for child in node:
            walk(child, dynamic)
            if not dynamic:
                value = normalize(child.tail)
                if value and not any(marker in value for marker in EXPRESSION_MARKERS):
                    units[tree.getpath(child) + "/tail()"] = value
    walk(root)
    return units


def static_images(root):
    """Yield only literal images, with empty alt as a decorative exception."""
    tree = root.getroottree()

    def walk(node, dynamic_parent=False):
        dynamic = dynamic_parent or _dynamic(node)
        if dynamic:
            return
        if etree.QName(node).localname.lower() == "img":
            alt = node.get("alt")
            alt_text = normalize(alt).casefold()
            decorative = (
                alt == "" or node.get("role") == "presentation"
                or node.get("aria-hidden", "").lower() == "true"
            )
            if not decorative and (not alt_text or alt_text in GENERIC_ALT):
                yield tree.getpath(node) + "/@alt"
        for child in node:
            yield from walk(child)
    yield from walk(root)


def compare_arches(source_arch, target_arch, ignored_terms=()):
    source = parse_arch(source_arch)
    target = parse_arch(target_arch)
    source_units = static_units(source)
    target_units = static_units(target)
    ignored = {normalize(term).casefold() for term in ignored_terms if normalize(term)}
    results = []

    for path in static_images(target):
        results.append(("missing_alt", "warning", path[:240], digest(path)))

    for path, text in source_units.items():
        target_text = target_units.get(path)
        if (
            len(text) >= MIN_TEXT_LENGTH
            and target_text is not None
            and text.casefold() == target_text.casefold()
            and text.casefold() not in ignored
        ):
            results.append(("identical_text", "info", path[:240], digest(text)))
    return results

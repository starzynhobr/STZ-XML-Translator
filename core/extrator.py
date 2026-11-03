from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedEntry:
    """A translatable XML value plus metadata from its containing record."""

    xpath: str
    container_xpath: str
    source_tag: str
    original: str
    context: dict[str, str] = field(default_factory=dict)


@dataclass
class XmlDocumentIndex:
    """Parsed XML plus immutable indexes reused during one editing session."""

    path: str
    size: int
    mtime_ns: int
    root: ET.Element
    parent_map: dict[ET.Element, ET.Element]
    elements_by_tag: dict[str, list[ET.Element]]
    parent_tags: list[str]
    child_tags_by_parent: dict[str, list[str]]

    def matches_file(self, path: str) -> bool:
        try:
            stat = os.stat(path)
        except OSError:
            return False
        return (
            os.path.abspath(path) == self.path
            and stat.st_size == self.size
            and stat.st_mtime_ns == self.mtime_ns
        )

    def child_tags(self, parent_tag: str) -> list[str]:
        return list(self.child_tags_by_parent.get(parent_tag.strip(), []))

    def preview(
        self,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> dict[str, int]:
        targets = _unique_tags(target_tags)
        contexts = _unique_tags(context_tags)
        if not targets or any(tag in contexts for tag in targets):
            return {"records": 0, "lines": 0}

        selected_parent = parent_tag.strip()
        if not selected_parent:
            record_elements: set[ET.Element] = set()
            lines = 0
            for target_tag in targets:
                for target in self.elements_by_tag.get(target_tag, []):
                    if _element_text(target):
                        lines += 1
                        record_elements.add(self.parent_map.get(target, self.root))
            return {"records": len(record_elements), "lines": lines}

        target_set = set(targets)
        containers = self.elements_by_tag.get(selected_parent, [])
        records = 0
        lines = 0
        for container in containers:
            matches = sum(
                1
                for child in container
                if _local_name(child.tag) in target_set and _element_text(child)
            )
            if matches:
                records += 1
                lines += matches
        return {"records": records, "lines": lines}

    def extract_entries(
        self,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> tuple[bool, list[ExtractedEntry] | str]:
        targets = _unique_tags(target_tags)
        contexts = _unique_tags(context_tags)

        if not targets:
            return False, "AVISO: Selecione pelo menos uma tag alvo."

        overlap = [tag for tag in targets if tag in contexts]
        if overlap:
            joined = ", ".join(f"<{tag}>" for tag in overlap)
            return False, f"AVISO: {joined} não pode ser alvo e contexto ao mesmo tempo."

        entries: list[ExtractedEntry] = []
        # The old implementation rescanned every sibling for every XPath. Sharing
        # this cache makes each (parent, tag) sibling group get indexed only once.
        sibling_indexes: dict[tuple[ET.Element, str], dict[ET.Element, int]] = {}
        selected_parent = parent_tag.strip()

        if selected_parent:
            containers = self.elements_by_tag.get(selected_parent, [])
            for container in containers:
                context = _collect_context(container, contexts)
                container_xpath = _indexed_xpath(
                    container, self.root, self.parent_map, sibling_indexes
                )
                for target_tag in targets:
                    for target in _matching_children(container, target_tag):
                        original = _element_text(target)
                        if not original:
                            continue
                        entries.append(
                            ExtractedEntry(
                                xpath=_indexed_xpath(
                                    target, self.root, self.parent_map, sibling_indexes
                                ),
                                container_xpath=container_xpath,
                                source_tag=target_tag,
                                original=original,
                                context=dict(context),
                            )
                        )
        else:
            for target_tag in targets:
                for target in self.elements_by_tag.get(target_tag, []):
                    original = _element_text(target)
                    if not original:
                        continue
                    container = self.parent_map.get(target, self.root)
                    entries.append(
                        ExtractedEntry(
                            xpath=_indexed_xpath(
                                target, self.root, self.parent_map, sibling_indexes
                            ),
                            container_xpath=_indexed_xpath(
                                container, self.root, self.parent_map, sibling_indexes
                            ),
                            source_tag=target_tag,
                            original=original,
                            context=_collect_context(container, contexts),
                        )
                    )

        if not entries:
            selected = ", ".join(f"<{tag}>" for tag in targets)
            scope = f" dentro de <{selected_parent}>" if selected_parent else ""
            return False, f"AVISO: Nenhum texto foi encontrado nas tags {selected}{scope}."
        return True, entries


@dataclass(frozen=True)
class Group:
    """One record tag and its fields: part of a selection over one XML file."""

    parent: str
    targets: tuple[str, ...]
    contexts: tuple[str, ...] = ()

    @classmethod
    def of(cls, parent: str, targets: Sequence[str], contexts: Sequence[str] = ()) -> Group:
        clean_targets = tuple(_unique_tags(targets))
        clean_contexts = tuple(tag for tag in _unique_tags(contexts) if tag not in clean_targets)
        return cls(parent.strip(), clean_targets, clean_contexts)

    def to_json(self) -> dict:
        return {"parent": self.parent, "targets": list(self.targets), "contexts": list(self.contexts)}


def extract_groups(index: XmlDocumentIndex, groups: Sequence[Group]) -> tuple[bool, list[ExtractedEntry] | str]:
    """Entries of every group, in group order; a group without text is skipped."""
    entries: list[ExtractedEntry] = []
    seen: set[str] = set()
    first_error = ""
    for group in groups:
        ok, result = index.extract_entries(group.parent, group.targets, group.contexts)
        if not ok or isinstance(result, str):
            first_error = first_error or str(result)
            continue
        for entry in result:
            if entry.xpath not in seen:
                seen.add(entry.xpath)
                entries.append(entry)
    if not entries:
        return False, first_error or "AVISO: Selecione pelo menos uma tag alvo."
    return True, entries


def _local_name(tag: str) -> str:
    """Return an element's local tag name, with an XML namespace removed."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _unique_tags(tags: Sequence[str]) -> list[str]:
    """Normalize a tag selection while preserving the user's order."""
    result: list[str] = []
    for tag in tags:
        normalized = str(tag).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _element_text(element: ET.Element) -> str:
    """Read direct element text without flattening nested XML content."""
    return (element.text or "").strip()


def _matching_children(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == tag]


def _collect_context(container: ET.Element, context_tags: Sequence[str]) -> dict[str, str]:
    context: dict[str, str] = {}
    for tag in context_tags:
        values = [
            text
            for child in _matching_children(container, tag)
            if (text := _element_text(child))
        ]
        if values:
            context[tag] = "\n".join(values)
    return context


def _xpath_segment(element: ET.Element, siblings: Sequence[ET.Element]) -> str:
    local_name = _local_name(element.tag)
    same_name = [sibling for sibling in siblings if _local_name(sibling.tag) == local_name]
    index = same_name.index(element) + 1
    if "}" in element.tag:
        return f"*[local-name()='{local_name}'][{index}]"
    return f"{element.tag}[{index}]"


def _indexed_xpath(
    elem: ET.Element,
    root: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    sibling_indexes: dict[tuple[ET.Element, str], dict[ET.Element, int]],
) -> str:
    """Generate the legacy-compatible XPath without quadratic sibling scans."""
    path_parts: list[str] = []
    current = elem
    while current in parent_map:
        parent = parent_map[current]
        local_name = _local_name(current.tag)
        cache_key = (parent, local_name)
        indexes = sibling_indexes.get(cache_key)
        if indexes is None:
            indexes = {}
            position = 0
            for sibling in parent:
                if _local_name(sibling.tag) == local_name:
                    position += 1
                    indexes[sibling] = position
            sibling_indexes[cache_key] = indexes
        index = indexes[current]
        if "}" in current.tag:
            path_parts.append(f"*[local-name()='{local_name}'][{index}]")
        else:
            path_parts.append(f"{current.tag}[{index}]")
        current = parent

    if "}" in root.tag:
        path_parts.append(f"*[local-name()='{_local_name(root.tag)}']")
    else:
        path_parts.append(str(root.tag))
    return "/" + "/".join(reversed(path_parts))


def indexar_xml(arquivo_xml: str) -> tuple[bool, XmlDocumentIndex | str]:
    """Parse and index a document once for structure preview and extraction."""
    try:
        stat = os.stat(arquivo_xml)
        root = ET.parse(arquivo_xml).getroot()
        parent_map: dict[ET.Element, ET.Element] = {}
        elements_by_tag: dict[str, list[ET.Element]] = defaultdict(list)
        child_order: dict[str, list[str]] = defaultdict(list)
        child_seen: dict[str, set[str]] = defaultdict(set)
        text_children: dict[str, set[str]] = defaultdict(set)
        repeating: set[str] = set()
        tags_with_text_children: set[str] = set()

        for element in root.iter():
            element_name = _local_name(element.tag)
            elements_by_tag[element_name].append(element)
            children = list(element)
            counts = Counter(_local_name(child.tag) for child in children)
            repeating.update(tag for tag, count in counts.items() if count > 1)

            for child in children:
                parent_map[child] = element
                child_name = _local_name(child.tag)
                if child_name not in child_seen[element_name]:
                    child_seen[element_name].add(child_name)
                    child_order[element_name].append(child_name)
                if _element_text(child):
                    tags_with_text_children.add(element_name)
                    text_children[element_name].add(child_name)

        parent_tags = sorted(repeating & tags_with_text_children)
        if not parent_tags:
            parent_tags = sorted(repeating)

        child_tags_by_parent = {}
        for parent_name, ordered_tags in child_order.items():
            text_tags = text_children[parent_name]
            child_tags_by_parent[parent_name] = (
                [tag for tag in ordered_tags if tag in text_tags]
                if text_tags
                else list(ordered_tags)
            )

        return True, XmlDocumentIndex(
            path=os.path.abspath(arquivo_xml),
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            root=root,
            parent_map=parent_map,
            elements_by_tag=dict(elements_by_tag),
            parent_tags=parent_tags,
            child_tags_by_parent=child_tags_by_parent,
        )
    except ET.ParseError as exc:
        filename = os.path.basename(arquivo_xml)
        return False, f"ERRO CRÍTICO: O arquivo '{filename}' não é um XML válido.\n\nDetalhes: {exc}"
    except Exception as exc:
        return False, f"ERRO INESPERADO durante a análise: {exc}"


def get_xpath(elem: ET.Element, root: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> str:
    """Generate a unique XPath accepted by lxml, including namespaced XML."""
    path_parts: list[str] = []
    current = elem
    while current in parent_map:
        parent = parent_map[current]
        path_parts.insert(0, _xpath_segment(current, list(parent)))
        current = parent

    if "}" in root.tag:
        root_part = f"*[local-name()='{_local_name(root.tag)}']"
    else:
        root_part = str(root.tag)
    path_parts.insert(0, root_part)
    return "/" + "/".join(path_parts)


def extrair_entradas(
    arquivo_xml: str,
    parent_tag: str,
    target_tags: Sequence[str],
    context_tags: Sequence[str] = (),
) -> tuple[bool, list[ExtractedEntry] | str]:
    """Extract multiple target fields and sibling context from an XML document.

    Each non-empty target element becomes an independent entry. Context is
    collected only from direct children of the same parent occurrence and is
    never itself returned as a translatable entry.
    """
    success, result = indexar_xml(arquivo_xml)
    if not success or isinstance(result, str):
        return False, result
    return result.extract_entries(parent_tag, target_tags, context_tags)


def extrair_textos(arquivo_xml: str, parent_tag: str, target_tag: str):
    """Backward-compatible single-target extraction returning ``{xpath: text}``."""
    success, result = extrair_entradas(arquivo_xml, parent_tag, [target_tag])
    if not success:
        return False, result
    return True, {entry.xpath: entry.original for entry in result}

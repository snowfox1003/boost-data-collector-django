"""
Minimal document types and recursive character text splitting for Pinecone ingestion.

Splitter behavior matches LangChain 0.2.x ``RecursiveCharacterTextSplitter`` /
``TextSplitter`` (MIT License) closely enough for chunk metadata (including
``start_index``) and merge logic used by this project.
"""

from __future__ import annotations

import copy
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Chunk or source document (page content + metadata for Pinecone)."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_text_with_regex(
    text: str,
    separator: str,
    keep_separator: bool | Literal["start", "end"],
) -> list[str]:
    """Split *text* on *separator* (regex); optionally keep delimiter segments."""
    if separator:
        if keep_separator:
            _splits = re.split(f"({separator})", text)
            splits = (
                ([_splits[i] + _splits[i + 1] for i in range(0, len(_splits) - 1, 2)])
                if keep_separator == "end"
                else ([_splits[i] + _splits[i + 1] for i in range(1, len(_splits), 2)])
            )
            if len(_splits) % 2 == 0:
                splits += _splits[-1:]
            splits = (
                (splits + [_splits[-1]])
                if keep_separator == "end"
                else ([_splits[0]] + splits)
            )
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


class TextSplitter(ABC):
    """Base splitter: merge token runs up to *chunk_size* with *chunk_overlap*."""

    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        keep_separator: bool | Literal["start", "end"] = False,
        add_start_index: bool = False,
        strip_whitespace: bool = True,
    ) -> None:
        """Configure chunk length, overlap, and optional ``start_index`` in chunk metadata."""
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"Got a larger chunk overlap ({chunk_overlap}) than chunk size "
                f"({chunk_size}), should be smaller."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._keep_separator: bool | Literal["start", "end"] = keep_separator
        self._add_start_index = add_start_index
        self._strip_whitespace = strip_whitespace

    @abstractmethod
    def split_text(self, text: str) -> list[str]:
        """Return non-overlapping string chunks for *text*."""
        raise NotImplementedError

    def create_documents(
        self, texts: list[str], metadatas: list[dict[str, Any]] | None = None
    ) -> list[Document]:
        """Split each string in *texts* into ``Document`` rows with copied *metadatas*."""
        _metadatas = metadatas or [{}] * len(texts)
        documents: list[Document] = []
        for i, text in enumerate(texts):
            index = 0
            previous_chunk_len = 0
            for chunk in self.split_text(text):
                metadata = copy.deepcopy(_metadatas[i])
                if self._add_start_index:
                    offset = index + previous_chunk_len - self._chunk_overlap
                    index = text.find(chunk, max(0, offset))
                    metadata["start_index"] = index
                    previous_chunk_len = len(chunk)
                documents.append(Document(page_content=chunk, metadata=metadata))
        return documents

    def split_documents(self, documents: Iterable[Document]) -> list[Document]:
        """Split each ``Document.page_content``; metadata is deep-copied per chunk."""
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for doc in documents:
            texts.append(doc.page_content)
            metadatas.append(doc.metadata)
        return self.create_documents(texts, metadatas=metadatas)

    def _join_docs(self, docs: list[str], separator: str) -> str | None:
        """Join *docs* with *separator*; strip if configured; return None for empty."""
        text = separator.join(docs)
        if self._strip_whitespace:
            text = text.strip()
        if text == "":
            return None
        return text

    def _merge_splits(self, splits: Iterable[str], separator: str) -> list[str]:
        """Combine small *splits* into chunks not exceeding *chunk_size* (with overlap trim)."""
        separator_len = self._length_function(separator)

        docs: list[str] = []
        current_doc: list[str] = []
        total = 0
        for d in splits:
            _len = self._length_function(d)
            if (
                total + _len + (separator_len if len(current_doc) > 0 else 0)
                > self._chunk_size
            ):
                if total > self._chunk_size:
                    logger.warning(
                        "Created a chunk of size %s, which is longer than the specified %s",
                        total,
                        self._chunk_size,
                    )
                if len(current_doc) > 0:
                    doc = self._join_docs(current_doc, separator)
                    if doc is not None:
                        docs.append(doc)
                    while total > self._chunk_overlap or (
                        total + _len + (separator_len if len(current_doc) > 0 else 0)
                        > self._chunk_size
                        and total > 0
                    ):
                        total -= self._length_function(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc = current_doc[1:]
            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)
        doc = self._join_docs(current_doc, separator)
        if doc is not None:
            docs.append(doc)
        return docs


class RecursiveCharacterTextSplitter(TextSplitter):
    """Split by trying ``separators`` in order (paragraph, line, space, then chars)."""

    def __init__(
        self,
        separators: list[str] | None = None,
        keep_separator: bool | Literal["start", "end"] = True,
        is_separator_regex: bool = False,
        **kwargs: Any,
    ) -> None:
        """Defaults match common LangChain behavior (``keep_separator=True``)."""
        super().__init__(keep_separator=keep_separator, **kwargs)
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split *text* using the first matching separator, then merge."""
        final_chunks: list[str] = []
        separator = separators[-1]
        new_separators: list[str] = []
        for i, _s in enumerate(separators):
            _separator = _s if self._is_separator_regex else re.escape(_s)
            if _s == "":
                separator = _s
                break
            if re.search(_separator, text):
                separator = _s
                new_separators = separators[i + 1 :]
                break

        _separator = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex(text, _separator, self._keep_separator)

        _separator = "" if self._keep_separator else separator
        _good_splits: list[str] = []
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _separator)
            final_chunks.extend(merged_text)
        return final_chunks

    def split_text(self, text: str) -> list[str]:
        """Public entry: split *text* with this instance's separator list."""
        return self._split_text(text, self._separators)

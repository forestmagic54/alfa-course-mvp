"""Russian-friendly lexical TF-IDF: words plus character n-grams, no downloads."""

from __future__ import annotations

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .text_utils import clean_text


class TextFeatures:
    def __init__(self) -> None:
        self.vectorizers: list[tuple[TfidfVectorizer, float]] = []
        self.matrix = sparse.csr_matrix((0, 0))

    def fit(self, texts: list[str]) -> TextFeatures:
        texts = [clean_text(t) for t in texts]
        self.vectorizers = []
        parts = []
        for options, weight in [
            (
                {
                    "analyzer": "word",
                    "ngram_range": (1, 2),
                    "token_pattern": r"(?u)\b\w\w+\b",
                },
                0.7,
            ),
            ({"analyzer": "char_wb", "ngram_range": (3, 5)}, 0.3),
        ]:
            vectorizer = TfidfVectorizer(
                sublinear_tf=True, max_features=60000, **options
            )
            if not texts or not any(texts):
                continue
            try:
                matrix = vectorizer.fit_transform(texts)
            except ValueError as error:
                if "empty vocabulary" not in str(error):
                    raise
                continue
            self.vectorizers.append((vectorizer, weight))
            parts.append(matrix * np.sqrt(weight))
        self.matrix = (
            normalize(sparse.hstack(parts).tocsr())
            if parts
            else sparse.csr_matrix((len(texts), 0))
        )
        return self

    def transform(self, text: str) -> sparse.csr_matrix:
        parts = [
            v.transform([clean_text(text)]) * np.sqrt(w) for v, w in self.vectorizers
        ]
        return (
            normalize(sparse.hstack(parts).tocsr())
            if parts
            else sparse.csr_matrix((1, 0))
        )

    def query_scores(self, text: str) -> np.ndarray:
        return (self.matrix @ self.transform(text).T).toarray().ravel()


class FieldTextFeatures(TextFeatures):
    """Experimental shared-vocabulary field weighting; never downloads models."""

    def fit_fields(self, rows, weights=(0.45, 0.30, 0.25)):
        fields = [
            [r["title"] for r in rows],
            [r["description"] for r in rows],
            [" ".join(r["topics"] + r["tags"] + r["industries"]) for r in rows],
        ]
        self.fit([" ".join(parts) for parts in zip(*fields, strict=False)])
        matrices = []
        for texts in fields:
            parts = [
                v.transform([clean_text(t) for t in texts]) * np.sqrt(w)
                for v, w in self.vectorizers
            ]
            matrices.append(normalize(sparse.hstack(parts).tocsr()))
        self.matrix = normalize(sum(w * m for w, m in zip(weights, matrices, strict=False))).tocsr()
        return self

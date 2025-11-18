from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def compute_similarities(
    corpus: List[str],
    query_index: int,
    top_k: int = 5,
) -> List[Tuple[int, float]]:
    """
    corpus: Liste von Texten (z.B. ocr_text aller Dokumente)
    query_index: Index des Referenzdokuments im corpus
    Rückgabe: Liste (index, score), absteigend sortiert, ohne sich selbst.
    """
    if not corpus:
        return []

    vectorizer = TfidfVectorizer(max_features=5000)
    X = vectorizer.fit_transform(corpus)

    sims = cosine_similarity(X[query_index:query_index+1], X).flatten()
    scores = [(i, float(sims[i])) for i in range(len(corpus)) if i != query_index]
    scores.sort(key=lambda t: t[1], reverse=True)
    return scores[:top_k]

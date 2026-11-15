"""Retrieval over the NAM knowledge base (observations, gazetteer, datasets).

Pure-Python TF-IDF with cosine similarity; no external index dependency.
The production path upgrades to bge-small-en-v1.5 embeddings + sqlite-vec /
LanceDB behind the same interface.
"""
import math
import re

_DOCS = None
_INDEX = None


_STOPWORDS = {"the", "a", "an", "of", "on", "in", "and", "or", "to", "is", "are", "for",
              "with", "at", "by", "from", "that", "this", "it", "what", "which", "how",
              "does", "do", "my", "me", "you", "about", "near", "around"}


def _tokenize(text):
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
            if t not in _STOPWORDS]


def _build():
    global _DOCS, _INDEX
    if _INDEX is not None:
        return
    from .. import seeds as s  # noqa: F401  (avoid cycle at import time)
    docs = []
    for o in s.observations():
        text = o["title"] + " " + o["summary"] + " " + " ".join(o.get("tags", []))
        docs.append({"kind": "discovery", "id": o["id"], "title": o["title"],
                     "text": text, "lat": o["lat"], "lon": o["lon"],
                     "citation": o["evidence"]["citation"], "url": o["evidence"].get("url")})
    for f in s.features():
        if f.get("note"):
            docs.append({"kind": "gazetteer", "id": f["id"], "title": f["name"],
                         "text": f["name"] + " " + (f.get("type") or "") + " " + (f.get("note") or ""),
                         "lat": f["lat"], "lon": f["lon"], "citation": f.get("src")})
    for d in s.datasets():
        docs.append({"kind": "dataset", "id": d["id"], "title": d["name"],
                     "text": d["name"] + " " + d["org"] + " " + (d.get("note") or ""),
                     "lat": None, "lon": None, "citation": d["url"]})
    for w in s.water_all():
        docs.append({"kind": "water", "id": w["id"], "title": w["name"],
                     "text": w["name"] + " " + w["note"] + " water ice",
                     "lat": w["lat"], "lon": w["lon"], "citation": w["src"]})
    for sh in s.shelters_all():
        docs.append({"kind": "shelter", "id": sh["id"], "title": sh["name"],
                     "text": sh["name"] + " " + sh["type"] + " " + sh["note"],
                     "lat": sh["lat"], "lon": sh["lon"], "citation": "NAM curated shelter set [SIM]"})
    _DOCS = docs
    df = {}
    for d in docs:
        for t in set(_tokenize(d["text"])):
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
    vecs = []
    for d in docs:
        tf = {}
        for t in _tokenize(d["text"]):
            tf[t] = tf.get(t, 0) + 1
        vec = {t: (1 + math.log(c)) * idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vecs.append({t: v / norm for t, v in vec.items()})
    _INDEX = {"idf": idf, "vecs": vecs}


def search(qq, k=5):
    _build()
    tf = {}
    for t in _tokenize(qq):
        tf[t] = tf.get(t, 0) + 1
    qv = {t: (1 + math.log(c)) * _INDEX["idf"].get(t, 1.0) for t, c in tf.items()}
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
    hits = []
    for i, vec in enumerate(_INDEX["vecs"]):
        score = 0.0
        for t, v in qv.items():
            if t in vec:
                score += v * vec[t]
        score /= qn
        if score > 0.12:
            d = _DOCS[i]
            hits.append({"score": round(score, 3), "kind": d["kind"], "id": d["id"],
                         "title": d["title"], "lat": d["lat"], "lon": d["lon"],
                         "citation": d["citation"], "url": d.get("url")})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def rank_listings(applicant_skills: str, listings: list[dict]) -> list[dict]:
    """
    Rank a list of job listings by similarity to the applicant's
    stated skills.

    Parameters
    ----------
    applicant_skills : str
        Free-text string of the applicant's skills, e.g. "python flask sql".
    listings : list[dict]
        Each dict must have a "skills" key (free-text required skills).

    Returns
    -------
    list[dict]
        The same listing dicts, each with an added "match_score" (0-100),
        sorted from best match to worst match.
    """
    if not applicant_skills.strip() or not listings:
        return []

    # Build the corpus: applicant profile first, then every listing's skills.
    corpus = [applicant_skills] + [listing["skills"] for listing in listings]

    # TF-IDF turns each text into a weighted vector of terms.
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # Cosine similarity between the applicant vector (row 0) and every
    # listing vector (rows 1..N): this is the actual "AI matching" step.
    applicant_vector = tfidf_matrix[0:1]
    listing_vectors = tfidf_matrix[1:]
    scores = cosine_similarity(applicant_vector, listing_vectors)[0]

    ranked = []
    for listing, score in zip(listings, scores):
        entry = dict(listing)
        entry["match_score"] = round(float(score) * 100, 1)
        ranked.append(entry)

    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return ranked

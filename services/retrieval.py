from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
from time import perf_counter
from sqlalchemy.orm import Session

from database.crud.chunk import get_chunks_by_ids
from services.ingest import embedding


load_dotenv(override=True)
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = os.getenv("QDRANT_PORT")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
RERANKER_MODEL = os.getenv("RERANKER_MODEL")
LIMIT = int(os.getenv("LIMIT"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K"))

reranker = CrossEncoder(RERANKER_MODEL, device="cuda", local_files_only=True)
client = QdrantClient(port=QDRANT_PORT, location=QDRANT_HOST)

collection = COLLECTION_NAME
limit = LIMIT


def retrieval(db : Session, question : str) -> list:
    """
    search relevant document from qdrant
    
    Args:
        question : User question

    Returns:
        list[dict]: list of retrivead chunks
    """
    start = perf_counter()
    vector = embedding.encode(question, prompt_name="query", normalize_embeddings=True)
    embedding_time = perf_counter() - start
    qdrant_start = perf_counter()
    result = client.query_points(collection_name=COLLECTION_NAME, 
                                 query= vector.tolist(),
                                 with_payload=True,
                                 limit=limit)
    points = result.points
    chunk_ids = [point.payload["chunk_id"] for point in points]
    qdrant_time = perf_counter() - qdrant_start

    db_start = perf_counter()
    chunks = get_chunks_by_ids(db, chunk_ids=chunk_ids)
    db_time = perf_counter() - db_start

    reranker_start = perf_counter()
    pairs = [[question, chunk.text] for chunk in chunks]
    scores = reranker.predict(pairs)
    reranker_time = perf_counter() - reranker_start
    
    scored_docs = list(zip(chunks, scores))
    ranked_docs = sorted(
        scored_docs,
        key=lambda x : x[1],
        reverse=True
    )
    total_time = perf_counter() - start
    print({
    "embedding_seconds": round(embedding_time, 2),
    "qdrant_seconds": round(qdrant_time, 2),
    "db_seconds": round(db_time, 2),
    "reranker_seconds": round(reranker_time, 2),
    "total time" : round(total_time)
})
    return ranked_docs[:RERANK_TOP_K]

if __name__ =="__main__" :
    result = retrieval("cara resend FSC di HUMS?")
    print(result)
    
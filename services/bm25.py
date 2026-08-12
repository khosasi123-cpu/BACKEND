import pickle
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
import re

from database.crud.chunk import get_all_chunk
from database.database import SessionLocal


load_dotenv(override=True)

BM25_PATH = os.getenv("BM25_PATH")

def tokenize(text: str) -> list[str]:
    text = text.lower()
    return re.findall(
        r"[a-z0-9]+(?:[-._][a-z0-9]+)*",
        text
    )

class BM25Index:

    def __init__(self):
        self.bm25 = None
        self.chunk_ids = []

    def load(self):
        with open(BM25_PATH, "rb") as f:
            data = pickle.load(f)

        self.bm25 = data["bm25"]
        self.chunk_ids = data["chunk_id"] 

    def build(self, db: Session):
        chunks = get_all_chunk(db)

        tokenized_corpus = [
            tokenize(chunk.text)
            for chunk in chunks
        ]

        self.bm25 = BM25Okapi(tokenized_corpus)

        self.chunk_ids = [
            chunk.id
            for chunk in chunks
        ]

        with open(BM25_PATH, "wb") as f:
            pickle.dump(
                {
                    "bm25": self.bm25,
                    "chunk_id": self.chunk_ids,
                },
                f
            )

    def search(
        self,
        question: str,
        limit: int = 10
    ):
        scores = self.bm25.get_scores(
            tokenize(question)
        )

        top_indices = scores.argsort()[::-1][:limit]

        return [
            self.chunk_ids[i]
            for i in top_indices
        ]

bm25_index = BM25Index()

if __name__ == "__main__":
    from database.database import get_db, SessionLocal
    db = get_db()
    bm25_index.build(next(db))
    db.close()
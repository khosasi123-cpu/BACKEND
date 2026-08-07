from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, FilterSelector, Filter, FieldCondition, MatchValue
from pathlib import Path
import glob
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
import random

from database.model.chunk import Chunk
from database.crud.chunk import create_chunks

load_dotenv(override=True)
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = os.getenv("QDRANT_PORT")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
BASE_FOLDER = Path(__file__).parent.parent / "data"
#FOLDERS = [p for p in BASE_FOLDER.iterdir() if p.is_dir()]

#load embeddingt model
embedding = SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)

#crete collection
client = QdrantClient(host=QDRANT_HOST, port= QDRANT_PORT)
def init_vector_db():
    if client.collection_exists(COLLECTION_NAME):
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=1024,
            distance=Distance.COSINE,
        ),
    )                        


# def load_file():
#     documents = []
#     for folder in FOLDERS:
#         load_files = DirectoryLoader(folder ,glob="**/*md", loader_cls=TextLoader, loader_kwargs={'encoding': 'utf-8'})
#         for doc in load_files.load() :
#             doc.metadata["document_name"] = Path(doc.metadata["source"]).name
#             documents.append(doc)
#     print(f"jumlah documnet yang di load : {len(documents)}")
#     return documents

def create_chunk(
    db: Session,
    documents: list[Document]
) -> list[Document]:

    chunk_counter = {}
    chunk_models = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=300
    )

    chunks = splitter.split_documents(documents)

    for chunk in chunks:

        document_id = chunk.metadata["document_id"]

        if document_id not in chunk_counter:
            chunk_counter[document_id] = 0

        chunk_index = chunk_counter[document_id]

        chunk.metadata["chunk_index"] = chunk_index
        chunk.metadata["chunk_id"] = f"{document_id}:{chunk_index}"

        chunk_models.append(
            Chunk(
                id=chunk.metadata["chunk_id"],
                document_id=document_id,
                chunk_index=chunk_index,
                text=chunk.page_content
            )
        )

        chunk_counter[document_id] += 1

    create_chunks(
        db=db,
        chunks=chunk_models
    )
    print(f"jumlah chunk yang di buat : {len(chunk_models)}")
    return chunks



def create_vector(chunks):
    texts = [c.page_content for c in chunks]
    vectors = embedding.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    print(f"jumlah chunk yang di embedding ada :{len(vectors)}")
    print(f"tiap chunk punya {len(vectors[0])} dimensi")
    return vectors

def create_point(chunks , vectors):
    points = []
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):

        payload = {
            "document_id": chunk.metadata["document_id"],
            "chunk_id": chunk.metadata["chunk_id"],
        }

        point = PointStruct(
            id = random.getrandbits(64), # generate unique id for each point
            vector=vector.tolist(), # perlu tolist agar sebelumnya dari arralu numpy jadi list python yang di mau qdrant
            payload=payload
        )
        points.append(point)
    return points

def insert_to_qdrant(points):
    client.upsert(collection_name="knowledge-base",
                  points=points,
                  )

def ingest_new_document(db: Session, document: list[Document]):
    chunk = create_chunk(db=db, documents=document)
    vector = create_vector(chunk)
    point = create_point(chunk, vector)
    try: 
        insert_to_qdrant(point)
        print("document succesfully uploaded")
    except Exception as e:
        print(e)
        raise

def delete_document_vector(document_id:str):
    operation = client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
        )
    )
    print(operation)


# if __name__ == "__main__" :
#     docs = load_file()
#     chunks = create_chunk(docs)
#     vectors = create_vector(chunks)
#     points = create_point(chunks, vectors)
#     insert_to_qdrant(points)
     


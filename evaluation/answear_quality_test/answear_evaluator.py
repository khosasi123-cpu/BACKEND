import sys
import math
from urllib import response
from pydantic import BaseModel, Field
from litellm import completion
from dotenv import load_dotenv
from uuid import uuid4
from dotenv import load_dotenv
import os
from openai import OpenAI
from sqlalchemy.orm import Session

from evaluation.answear_quality_test.answear_loader import TestQuestion, load_tests
from services.retrieval import retrieval
from services.chat import chat
from schemas.chat import ChatRequest
from database.database import SessionLocal


load_dotenv(override=True)

MODEL = "mistralai/Ministral-3-8B-Instruct-2512"
base_url = "http://localhost:8000/v1"
api_key = os.getenv("OPENAI_API_KEY")
OPENAI = OpenAI(base_url=base_url, api_key=api_key)

class RetrievalEval(BaseModel):
    """Evaluation metrics for retrieval performance."""

    mrr: float = Field(description="Mean Reciprocal Rank - average across all keywords")
    ndcg: float = Field(description="Normalized Discounted Cumulative Gain (binary relevance)")
    keywords_found: int = Field(description="Number of keywords found in top-k results")
    total_keywords: int = Field(description="Total number of keywords to find")
    keyword_coverage: float = Field(description="Percentage of keywords found")


class AnswerEval(BaseModel):
    """LLM-as-a-judge evaluation of English-to-Indonesian translation quality."""

    feedback: str = Field(
        description=(
            "Concise feedback comparing the Indonesian translation "
            "with the English source and reference translation."
        )
    )

    adequacy: float = Field(
        description=(
            "How accurately does the Indonesian translation preserve "
            "the meaning of the English source? "
            "1 = major mistranslation or missing meaning, "
            "5 = meaning is fully preserved."
        )
    )

    fluency: float = Field(
        description=(
            "How natural, grammatical, clear, and professional is the "
            "Indonesian translation? "
            "1 = very unnatural or difficult to understand, "
            "5 = natural and professionally written Indonesian."
        )
    )

    terminology: float = Field(
        description=(
            "How correctly does the translation handle technical terminology, "
            "product names, error codes, commands, acronyms, numbers, paths, "
            "and other domain-specific identifiers? "
            "1 = major terminology errors, "
            "5 = technical terminology and identifiers are correctly preserved."
        )
    )


def calculate_mrr(keyword: str, retrieved_docs: list) -> float:
    """Calculate reciprocal rank for a single keyword (case-insensitive)."""
    keyword_lower = keyword.lower()
    for rank, doc in enumerate(retrieved_docs, start=1):
        if keyword_lower in doc.lower():
            return 1.0 / rank
    return 0.0


def calculate_dcg(relevances: list[int], k: int) -> float:
    """Calculate Discounted Cumulative Gain."""
    dcg = 0.0
    for i in range(min(k, len(relevances))):
        dcg += relevances[i] / math.log2(i + 2)  # i+2 because rank starts at 1
    return dcg


def calculate_ndcg(keyword: str, retrieved_docs: list, k: int = 10) -> float:
    """Calculate nDCG for a single keyword (binary relevance, case-insensitive)."""
    keyword_lower = keyword.lower()

    # Binary relevance: 1 if keyword found, 0 otherwise
    relevances = [
        1 if keyword_lower in doc.lower() else 0 for doc in retrieved_docs[:k]
    ]

    # DCG
    dcg = calculate_dcg(relevances, k)

    # Ideal DCG (best case: keyword in first position)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = calculate_dcg(ideal_relevances, k)

    return dcg / idcg if idcg > 0 else 0.0


def evaluate_retrieval(db: Session, test: TestQuestion, k: int = 10) -> RetrievalEval:
    """
    Evaluate retrieval performance for a test question.

    Args:
        test: TestQuestion object containing question and keywords
        k: Number of top documents to retrieve (default 10)

    Returns:
        RetrievalEval object with MRR, nDCG, and keyword coverage metrics
    """
    # Retrieve documents using shared answer module
    retrieved = retrieval(db=db, question=test.question)
    retrieved_docs = [chunk.text for chunk, score in retrieved]

    # Calculate MRR (average across all keywords)
    mrr_scores = [calculate_mrr(keyword, retrieved_docs) for keyword in test.keywords]
    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0

    # Calculate nDCG (average across all keywords)
    ndcg_scores = [calculate_ndcg(keyword, retrieved_docs, k) for keyword in test.keywords]
    avg_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0

    # Calculate keyword coverage
    keywords_found = sum(1 for score in mrr_scores if score > 0)
    total_keywords = len(test.keywords)
    keyword_coverage = (keywords_found / total_keywords * 100) if total_keywords > 0 else 0.0

    return RetrievalEval(
        mrr=avg_mrr,
        ndcg=avg_ndcg,
        keywords_found=keywords_found,
        total_keywords=total_keywords,
        keyword_coverage=keyword_coverage,
    )


def evaluate_answer(db : Session, test: TestQuestion) -> tuple[AnswerEval, str, list]:
    """
    Evaluate answer quality using LLM-as-a-judge (async).

    Args:
        test: TestQuestion object containing question and reference answer

    Returns:
        Tuple of (AnswerEval object, generated_answer string, retrieved_docs list)
    """
    # Get RAG response using shared answer module
    response = chat(ChatRequest(
        question=test.question,
        session_id=str(uuid4())
    ), db=db)

    generated_answer = response.answer
    retrieved_docs = response.references

    # LLM judge prompt
    judge_messages = [
        {
                "role": "system",
                "content": """
        You are an expert evaluator for English-to-Indonesian technical translation.

        Evaluate the generated translation against the English source and reference
        translation. Score each dimension from 1 to 5.

        Adequacy: How accurately does the translation preserve the source meaning?
        Penalize mistranslation, missing meaning, changed meaning, or invented meaning.

        Fluency: How natural, grammatical, clear, and professional is the Indonesian?
        Do not penalize valid technical wording.

        Terminology: How correctly are technical terms, product names, error codes,
        commands, acronyms, numbers, paths, ports, and configuration values handled?
        Technical identifiers should remain unchanged when appropriate.

        Do not penalize differences in wording when the meaning is equivalent.
        5 means essentially ideal.

        Return only the requested structured evaluation.
        """
            },
            {
                "role": "user",
                "content": f"""
        English:
        {test.question}

        Generated:
        {generated_answer}

        Reference:
        {test.reference_answer}
        """
            },
        ]

    # Call LLM judge with structured outputs (async)
    response = OPENAI.responses.parse(
    model=MODEL,
    input=judge_messages,
    text_format=AnswerEval,
    temperature=0,
    max_output_tokens=2048,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    }
)

    answer_eval = response.output_parsed

    return answer_eval, generated_answer, retrieved_docs


def evaluate_all_retrieval():
    """Evaluate all retrieval tests."""
    db = SessionLocal()
    try:
        tests = load_tests()
        total_tests = len(tests)
        for index, test in enumerate(tests):
            result = evaluate_retrieval(db=db, test=test)
            progress = (index + 1) / total_tests
            yield test, result, progress
    finally:
        db.close()


def evaluate_all_answers():
    """Evaluate all answers to tests using batched async execution."""
    db = SessionLocal()
    try:
        tests = load_tests()
        total_tests = len(tests)
        for index, test in enumerate(tests):
            result = evaluate_answer(db=db, test=test)[0]
            progress = (index + 1) / total_tests
            yield test, result, progress
    finally:
        db.close()

def run_cli_evaluation(test_number: int):
    """Run evaluation for a specific test (async helper for CLI)."""
    # Load tests
    tests = load_tests("tests.jsonl")

    if test_number < 0 or test_number >= len(tests):
        print(f"Error: test_row_number must be between 0 and {len(tests) - 1}")
        sys.exit(1)

    # Get the test
    test = tests[test_number]

    # Print test info
    print(f"\n{'=' * 80}")
    print(f"Test #{test_number}")
    print(f"{'=' * 80}")
    print(f"Question: {test.question}")
    print(f"Keywords: {test.keywords}")
    print(f"Category: {test.category}")
    print(f"Reference Answer: {test.reference_answer}")

    # Retrieval Evaluation
    print(f"\n{'=' * 80}")
    print("Retrieval Evaluation")
    print(f"{'=' * 80}")

    retrieval_result = evaluate_retrieval(test)

    print(f"MRR: {retrieval_result.mrr:.4f}")
    print(f"nDCG: {retrieval_result.ndcg:.4f}")
    print(f"Keywords Found: {retrieval_result.keywords_found}/{retrieval_result.total_keywords}")
    print(f"Keyword Coverage: {retrieval_result.keyword_coverage:.1f}%")

    # Answer Evaluation
    print(f"\n{'=' * 80}")
    print("Answer Evaluation")
    print(f"{'=' * 80}")

    answer_result, generated_answer, retrieved_docs = evaluate_answer(test)

    print(f"\nGenerated Answer:\n{generated_answer}")
    print(f"\nFeedback:\n{answer_result.feedback}")
    print("\nScores:")
    print(f"  Accuracy: {answer_result.accuracy:.2f}/5")
    print(f"  Completeness: {answer_result.completeness:.2f}/5")
    print(f"  Relevance: {answer_result.relevance:.2f}/5")
    print(f"\n{'=' * 80}\n")


def main():
    """CLI to evaluate a specific test by row number."""
    if len(sys.argv) != 2:
        print("Usage: uv run eval.py <test_row_number>")
        sys.exit(1)

    try:
        test_number = int(sys.argv[1])
    except ValueError:
        print("Error: test_row_number must be an integer")
        sys.exit(1)

    run_cli_evaluation(test_number)


if __name__ == "__main__":
    main()

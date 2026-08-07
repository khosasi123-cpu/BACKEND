from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

import os
from time import perf_counter

from dotenv import load_dotenv

from schemas.chat import ChatRequest, ChatResponse, LLMResponse

from services import conversation as conversation_service
from services import message as message_service
from services.retrieval import retrieval
from services.router import router


load_dotenv(override=True)

MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

RAG_SYSTEM_PROMPT = """
You are a retrieval-grounded knowledge base assistant.

Answer the user's question using only the provided context.

Rules:
- Use only information supported by the context.
- Do not use external knowledge, assumptions, or invented information.
- Answer the question directly.
- Include all relevant information supported by the context and avoid unrelated details.
- You may summarize, combine, and clearly rephrase information from multiple context passages.
- Use steps or bullet points when they improve clarity.
- If the context supports only part of the question, answer the supported part and clearly state what could not be determined.
- If the context contains no sufficient information to answer the question, respond:
  "I could not find sufficient information in the knowledge base to answer that question."
- Do not reproduce large portions of the context unnecessarily.

Prioritize factual grounding while providing the most complete answer supported by the available context.

After answering, also return references using the required structured output.

Reference rules:
- Include only documents that were actually used to answer the question.
- For each document, include only image identifiers that are relevant to the answer.
- Image identifiers appear in the context as placeholders in the format:
  [Figure: image_filename]
- Do not invent document names or image identifiers.
- If no document is used, return an empty references list.
"""

SYSTEM_PROMPT = """
You are a conversational assistant for an internal knowledge assistant.

Use the user's message and conversation history to handle requests that do not require retrieving additional internal documentation.

You may:
- translate, summarize, rewrite, or format provided content
- clarify or simplify previous responses
- explain concepts or technical terms related to the current conversation
- continue the conversation using the available context

Rules:
- Preserve the meaning and technical terminology of provided content.
- You may use general knowledge to explain concepts, but do not present general knowledge as facts about the internal knowledge base, documents, systems, policies, or procedures.
- Do not invent missing details about internal documentation or previously discussed systems.
- If the user asks for a new internal fact that is not available in the conversation, state that the available conversation does not provide that information.
- Be concise unless the user requests more detail.
- Maintain the user's preferred language.
- For translation requests, return the translation directly unless additional explanation is requested.
"""


def build_context(results) -> str:
    return "\n\n---\n\n".join(
        f"""
===== SOURCE =====
Document: {chunk.document.document_name}
Chunk: {chunk.id}

{chunk.text}
"""
        for chunk, _ in results
    )


def chat(
    user_request: ChatRequest,
    db: Session
) -> ChatResponse:

    total_started = perf_counter()

    # ------------------------------------------------------------------
    # Conversation & History
    # ------------------------------------------------------------------

    history_started = perf_counter()

    if user_request.conversation_id is None:
        conversation = conversation_service.create_conversation(db=db)
    else:
        conversation = conversation_service.get_conversation(
            db=db,
            conversation_id=user_request.conversation_id
        )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    history = message_service.get_recent_messages(
        db=db,
        conversation_id=conversation.id
    )

    history_seconds = perf_counter() - history_started

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------

    router_started = perf_counter()

    router_result = router(
        user_request.question,
        history
    )

    router_seconds = perf_counter() - router_started

    print({
        "question": user_request.question[:100],
        "use_rag": router_result.use_rag,
        "rewritten_query": (
            router_result.rewritten_query[:100]
            if router_result.rewritten_query
            else None
        )
    })

    

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    if router_result.use_rag:

        query = (
            router_result.rewritten_query
            or user_request.question
        )

        retrieval_started = perf_counter()

        docs = retrieval(db=db, question=query)

        retrieval_seconds = perf_counter() - retrieval_started

        context = (
            build_context(docs)
            + f"\n\nThis is user question:\n{user_request.question}"
        )

        system_prompt = RAG_SYSTEM_PROMPT
        user_content = context

        

    else:

        retrieval_seconds = 0

        system_prompt = SYSTEM_PROMPT
        user_content = user_request.question

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": user_content}]
    )

    llm_started = perf_counter()

    response = OPENAI.responses.parse(
        model=MODEL,
        input=messages,
        text_format=LLMResponse,
        max_output_tokens=2048,
        temperature=0,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }
    )

    llm_seconds = perf_counter() - llm_started

    answer = response.output_parsed or ""

    # ------------------------------------------------------------------
    # Save Conversation
    # ------------------------------------------------------------------

    message_service.create_message(
        db=db,
        conversation_id=conversation.id,
        role="user",
        content=user_request.question
    )

    message_service.create_message(
        db=db,
        conversation_id=conversation.id,
        role="assistant",
        content=answer.answer,
    )

    generated_seconds = perf_counter() - total_started

    print({
        "history_seconds": round(history_seconds, 2),
        "router_seconds": round(router_seconds, 2),
        "retrieval_seconds": round(retrieval_seconds, 2),
        "llm_seconds": round(llm_seconds, 2),
        "generated_seconds": round(generated_seconds, 2),
    })


    return ChatResponse(
        conversation_id=conversation.id,
        answer=answer.answer,
        references=answer.references
    )
import os
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Literal


load_dotenv(override=True)
# OPENAI= OpenAI()
# MODEL = "gpt-5.4-nano"
base_url = os.getenv("LLM_BASE_URL")
api_key = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("MODEL")

OPENAI = OpenAI(base_url=base_url, api_key=api_key)

class RouterResponse(BaseModel):
    use_rag: bool
    rewritten_query: str | None = None
    


router_prompt = """
You are a routing assistant for an internal knowledge assistant.

Return JSON only:

{{
  "use_rag": boolean,
  "rewritten_query": string | null
}}

Use RAG when the request requires information from internal documentation or the knowledge base.

This includes questions about:
- procedures or workflows
- troubleshooting and errors
- systems, applications, or features
- configuration or maintenance
- policies, requirements, controls, or responsibilities
- follow-up questions that require additional documented information

Do NOT use RAG when the task can be completed using only user-provided text or conversation history.

This includes:
- greetings, small talk, or thanks
- translation
- summarization or rewriting
- formatting or markdown conversion
- grammar correction
- content generation that does not require internal documentation

Rules:
- If use_rag is true, rewrite the question as a standalone retrieval query.
- Resolve references from conversation history when needed.
- Preserve technical terms exactly.
- Do not answer the question.
- If use_rag is false, rewritten_query must be null.
- Return JSON only.

History:
{history}

User:
{question}
"""




def router(question, history):
    messages = [{"role" : "system", "content" : router_prompt.format(history=history, question=question)}, {"role" : "user", "content" : question}]
    response = OPENAI.responses.parse(
    model=MODEL,
    input=messages,
    text_format=RouterResponse,
    temperature=0
    )
    return response.output_parsed

if __name__ == "__main__" :
    history = []
    question = "cara buat resend FSC di HUMS?"
    route_result = router(question, history)
    print(route_result)

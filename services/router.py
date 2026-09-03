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
    route: Literal["rag", "chat", "translate"]
    rewritten_query: str | None = None
    


router_prompt = """
You are a routing assistant for an internal knowledge assistant.
Return JSON only:
{{
  "route": "chat" | "rag" | "translate",
  "rewritten_query": string | null
}}
Use "rag" when the request requires information from internal documentation
or the knowledge base. This includes:
- procedures or workflows
- troubleshooting and errors
- systems, applications, or features
- configuration or maintenance
- policies, requirements, controls, or responsibilities
- follow-up questions that require additional documented information

Use "translate" only if has_files is true AND the user explicitly asks to
translate the attached file, with no other request requiring internal
documentation. Never use "translate" if has_files is false, even if the user
asks about translating a file.

If the request combines file translation with something needing internal
documentation (e.g. "translate this then explain per our policy"), use "rag"
instead and rewrite the query around the documentation need.

Use "chat" when the request can be completed using only user-provided text,
conversation history, or general knowledge. This includes:
- greetings, small talk, or thanks
- translation of text given directly in the conversation (not a file)
- summarization or rewriting
- formatting or markdown conversion
- grammar correction
- content generation that does not require internal documentation

Rules:
- If route is "rag", rewrite the question as a standalone retrieval query.
- If route is "chat" or "translate", rewritten_query must be null.
- Resolve references from conversation history when needed.
- Preserve technical terms exactly.
- Do not answer the question.
- Return JSON only.

History:
{history}
Has attached files:
{has_files}
User:
{question}
"""




def router(question, history, has_files=False):
    messages = [{"role" : "system", "content" : router_prompt.format(history=history, question=question, has_files=has_files)}, {"role" : "user", "content" : question}]
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

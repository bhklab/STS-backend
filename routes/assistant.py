"""
AI assistant: sends the user's question to Gemini (via Vertex AI) and lets
Gemini query the database through our read-only GraphQL schema.

How it works:
  1. We give Gemini the GraphQL schema and one tool: run_graphql_query.
  2. Gemini either answers directly, or asks us to run a GraphQL query.
  3. We run the query, send the result back, and repeat until Gemini answers.

Required environment variables:
  GOOGLE_APPLICATION_CREDENTIALS  path to the service account JSON key file
  GOOGLE_CLOUD_PROJECT            the Google Cloud project id
Optional:
  GOOGLE_CLOUD_LOCATION           Vertex AI region (default "global")
  GEMINI_MODEL                    model id (default below)
"""

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel

from database_session import get_db_session
from routes.graphql import schema

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-pro")

# Stop after this many tool calls so a confused model can't loop forever.
MAX_TOOL_ROUNDS = 8

# Cut very large query results down so we don't overflow the model's context.
MAX_RESULT_CHARACTERS = 20000

SYSTEM_INSTRUCTION = f"""
You are the assistant for the Soft Tissue Sarcoma (STS) Portal.
Answer questions about the portal's clinical and pre-clinical data.

When you need data, call the run_graphql_query tool with a GraphQL query
written against this schema (field names are camelCase):

{schema.as_str()}

Rules:
- Only use fields that exist in the schema above.
- Ask for only the fields you need, and use a small "limit".
- To know which data types (RNA-seq, Mutation, ...) a dataset has, use the
  dataLayers field on datasets. Don't guess this from descriptions.
- A dataset's description and keyStudyFindings describe the original
  published study, NOT what the portal contains. Only dataLayers and the
  fields on samples and cell lines show what is actually loaded. If a kind of
  data (e.g. survival) is only mentioned in a description, say the original
  study has it but it is not available in the portal.
- Only state facts about the portal's data that came from a query result.
  If the data can't answer the question, say so plainly. Never make up data.
- Format answers with simple Markdown only.
"""

# Switch out format rule to this if agent output is incorrectly formatted: Format answers with simple Markdown only: headings, **bold**, and bullet or numbered lists. Do not use tables.

# Describe the one tool Gemini is allowed to call.
run_graphql_query_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="run_graphql_query",
            description="Run a read-only GraphQL query against the STS Portal database and return the JSON result.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "query": types.Schema(
                        type="STRING", description="The GraphQL query to run."
                    ),
                },
                required=["query"],
            ),
        )
    ]
)


class ChatRequest(BaseModel):
    prompt: str


def run_graphql_query(query: str, session) -> str:
    """Run a GraphQL query and return the result (or errors) as a JSON string."""
    result = schema.execute_sync(query, context_value={"session": session})

    if result.errors:
        output = {"errors": [str(error) for error in result.errors]}
    else:
        output = {"data": result.data}

    output_text = json.dumps(output, default=str)
    if len(output_text) > MAX_RESULT_CHARACTERS:
        output_text = (
            output_text[:MAX_RESULT_CHARACTERS] + " ...(truncated, use a smaller limit)"
        )
    return output_text


# A plain "def" (not async) so FastAPI runs it in a thread; the Gemini
# and database calls below are blocking.
@router.post("/chat", summary="Ask the AI assistant a question")
def chat(request: ChatRequest, session=Depends(get_db_session)):
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION"),
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[run_graphql_query_tool],
    )
    # Same settings, but Gemini is not allowed to call the tool and must answer.
    final_round_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[run_graphql_query_tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="NONE")
        ),
    )

    # The running conversation we send to Gemini each round.
    conversation = [types.Content(role="user", parts=[types.Part(text=request.prompt)])]
    queries_run = []

    for round_number in range(MAX_TOOL_ROUNDS + 1):
        print(round_number)
        # On the last round, make Gemini answer with what it has found so far.
        is_last_round = round_number == MAX_TOOL_ROUNDS
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=conversation,
            config=final_round_config if is_last_round else config,
        )

        # No tool calls means Gemini has written its final answer.
        if not response.function_calls:
            return {"answer": response.text, "queries": queries_run}

        # Keep Gemini's tool request in the conversation, then run each query.
        conversation.append(response.candidates[0].content)
        tool_results = []
        for function_call in response.function_calls:
            query = function_call.args.get("query", "")
            queries_run.append(query)
            tool_results.append(
                types.Part.from_function_response(
                    name=function_call.name,
                    response={"result": run_graphql_query(query, session)},
                )
            )
        conversation.append(types.Content(role="user", parts=tool_results))

    # Only reached if Gemini ignores the final-round setting above.
    raise HTTPException(
        status_code=500,
        detail="The assistant needed too many queries to answer. Try a simpler question.",
    )

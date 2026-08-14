import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

load_dotenv(override=True)

app = FastAPI(title="Soft Tissue Sarcoma Portal API", openapi_url="/api/v1/openapi.json", version=f"v{os.getenv('VERSION')}")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}

from openai import OpenAI
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os


load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPENROUTER_API_KEY_2"),
                    timeout=30.0
    )
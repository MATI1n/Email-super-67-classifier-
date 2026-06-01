from openai import OpenAI
from qdrant_client import QdrantClient,  models
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer("jinaai/jina-embeddings-v5-omni-nano", trust_remote_code=True,
                               model_kwargs={"default_task": "retrieval"})

load_dotenv()
client_llm = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPENROUTER_API_KEY_2"),
                    timeout=30.0
)

client_qdrant = QdrantClient(
    location="https://5579278d-b04b-4fbd-9539-a97af90de739.europe-west3-0.gcp.cloud.qdrant.io",
    api_key=os.getenv("QDRANT_API_KEY")
)

def get_metadata(query: str) -> json:
    answer_from_small_model = client_llm.chat.completions.create(
            model=os.getenv("BASE_MODEL_URL"),
            messages=[{"role": "system", "content": os.getenv("SMALL_MODEL_PROMPT")},
                      {"role": "user", "content": query}],
            temperature=0
    )
    metadata = answer_from_small_model.choices[0].message.content
    try:
        data = json.loads(metadata)
        return data
    except json.JSONDecodeError:
        print("Ошибка: модель вернула невалидный JSON")
        print("Сырой ответ модели:", metadata)
        raise json.JSONDecodeError("Модель вернула невалидный JSON")

def smart_search(query: str) -> str:
    embedded_query = embedder.encode_query(query)
    metadata = get_metadata(query)
    name = metadata["name"]
    email = metadata["email"]
    conditions = []
    
    if name:
        conditions.append(
            models.FieldCondition(
                key="sender",
                match=models.MatchText(text=name)
            )
        )
    if email:
        conditions.append(
            models.FieldCondition(
                key="sender",
                match=models.MatchText(text=email)
            )
        )

    qdrant_filter = None
    if conditions:
        qdrant_filter = models.Filter(should=conditions)
    
    search_result = client_qdrant.query_points(
        collection_name="email_classifier",
        query=embedded_query,
        query_filter=qdrant_filter,
        limit=1,
        with_payload=True
    )
    relevant_email_name = search_result.points[0].payload.get("email_name")
    
    inbox = Path("inbox")
    files = list(inbox.glob(f"*{relevant_email_name}*"))
    result = [file.read_text(encoding="utf-8", errors="ignore") for file in files]
    return result
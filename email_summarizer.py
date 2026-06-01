from dotenv import load_dotenv
from openai import OpenAI
from tqdm.notebook import tqdm
import os


load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPENROUTER_API_KEY_2"),
                    timeout=30.0
    )

def summarize_email(messages: list[str]) -> list[str]:
    if isinstance(messages, str):
        messages = [messages]
    
    responses = []
    for message in tqdm(messages, desc="Обработка сообщений моделью"): 
        answer = client.chat.completions.create(
            model=os.getenv("BASE_MODEL_URL"),
            messages=[{"role": "system", "content": os.getenv("PROMPT")},
                      {"role": "user", "content": message}]
        )
        responses.append(answer.choices[0].message.content)
        
    return responses
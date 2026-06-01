from dotenv import load_dotenv
from openai import OpenAI
from tqdm.notebook import tqdm
import os


load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPENROUTER_API_KEY_2"),
                    timeout=30.0
    )

SYSTEM_PROMPT = """Act as a Senior IT Support Coordinator. Analyze the following incoming support email and provide a structured summary. 

CRITICAL: Each field must start on a new line. Use the following format exactly:

Проблема: (1-sentence description of the technical problem)
ПО: (The specific application or hardware mentioned)
Приоритет: (Низкий/Средний/Высокий/Срочный based on business impact)
Настроение пользователя: (Briefly describe user's tone)
    
If the email is not about a technical problem, simply provide a 2-3 sentence summary.

ANSWER IN THE LANGUAGE OF THE USER. BY DEFAULT ANSWER IN RUSSIAN. 

Email Content:"""

def summarize_email(messages: list[str]) -> list[str]:
    if isinstance(messages, str):
        messages = [messages]
    
    responses = []
    for message in tqdm(messages, desc="Обработка сообщений моделью"): 
        answer = client.chat.completions.create(
            model=os.getenv("BASE_MODEL_URL"),
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": message}]
        )
        responses.append(answer.choices[0].message.content)
        
    return responses
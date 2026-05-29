import shutil
import json
import logging
import argparse
from os import listdir
from collections import Counter
from tqdm.contrib.concurrent import process_map
from pathlib import Path
from structures import Letter

logging.basicConfig(
    filename='classifier.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

INBOX_DIR = Path("inbox")
PROCESSED_DIR = Path("processed")
N_JOBS = 4

CATEGORIES = [
    "urgent",
    "alerts",
    "spam",
    "hr_documents",
    "newsletters",
    "unknown",
    "errors"
]


def setup_directories():
    if not PROCESSED_DIR.exists():
        PROCESSED_DIR.mkdir()
    for cat in CATEGORIES:
        (PROCESSED_DIR / cat).mkdir(exist_ok=True)


def classify_letter(letter: Letter) -> str:
    subject = (letter.subject or "").lower()
    text = (letter.text or "").lower()
    sender = (letter.sent_from_email or "").lower()



    spam_keywords = ["casino", "win", "discount", "скидк", "выигрыш", "реклама", "казино"]
    if any(keyword in subject or keyword in text for keyword in spam_keywords):
        return "spam"

    alert_keywords = ["alert", "grafana", "zabbix", "prometheus", "noreply", "daemon"]
    if any(keyword in sender for keyword in alert_keywords):
        return "alerts"

    urgent_keywords = ["urgent", "срочно", "критичн", "падает", "ошибка 500", "инцидент", "недоступен"]
    if any(keyword in subject or keyword in text for keyword in urgent_keywords):
        return "urgent"

    news_keywords = ["дайджест", "newsletter", "рассылка", "новост"]
    if any(keyword in subject or keyword in text for keyword in news_keywords):
        return "newsletters"

    hr_keywords = ["отпуск", "больничный", "инструкция", "согласование", "договор", "заявление"]
    if any(keyword in subject or keyword in text for keyword in hr_keywords):
        return "hr_documents"

    return "unknown"


def check_empty(file_path: Path, content: list[str]) -> bool:
    if not content:
        logger.warning(f"Empty file: {file_path}")
        logger.info(f"Classified {file_path} as errors")
        return True

    return False

def check_letter(file_path: Path, letter: Letter) -> bool:
    if not letter.subject or not letter.text or not letter.sent_from_email or not letter.date:
        logger.warning(f"Could not extract meaningful data from: {file_path}")
        logger.info(f"Classified {file_path} as errors")
        return True
    return False


def classify_file(file_path: Path) -> str:
    if file_path.suffix != ".txt":
        logger.warning(f"Invalid file format: {file_path}")
        logger.info(f"Classified {file_path} as errors")
        return "errors"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        if check_empty(file_path, content):
            return "errors"

        letter = Letter(content)

        if check_letter(file_path, letter):
            return "errors"

        category = classify_letter(letter)
        logger.info(f"Classified {file_path} as {category}")

        return category

    except IndexError:
        logger.warning(f"Index error during parsing of {file_path}. Classified as errors")
        return "errors"

    except Exception as e:
        logger.warning(f"Error occurred {e} during {file_path} parsing. Classified as errors")
        return "errors"

def move_file(file_path: Path, category: str) -> None:
    destination = PROCESSED_DIR / category / file_path.name
    try:
        shutil.move(str(file_path), str(destination))
    except Exception as e:
        logger.error(f"Failed to move file {file_path} to {destination}: {e}")



def main():
    if not INBOX_DIR.exists():
        logger.error(f"Directory {INBOX_DIR} does not exist.")
        print(f"Directory {INBOX_DIR} does not exist.")
        return

    setup_directories()

    files = listdir(INBOX_DIR)

    logger.info("Starting email classification.")

    file_paths = [INBOX_DIR / file_path for file_path in files]

    categories = process_map(classify_file,file_paths , max_workers=N_JOBS, desc="Classifying letters")

    stats = Counter(categories)

    process_map(move_file, file_paths, categories, max_workers=N_JOBS, desc="Moving to folders")

    logger.info("Classification finished.")


    with open("stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

    print("Classification completed successfully.")
    print("Statistics:")
    for cat, count in stats.items():
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A simple CLI tool for email classification.")
    parser.add_argument("-i", "--input", type=str, default="inbox", help="Input folder")
    parser.add_argument("-o", "--output", type=str, default="processed", help="Output folder")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="Amount of CPU cores to use")

    args = parser.parse_args()


    INBOX_DIR = Path(args.input)
    PROCESSED_DIR = Path(args.output)
    N_JOBS = args.jobs
    main()

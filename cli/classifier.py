import shutil
import json
import logging
import argparse
import os
from dotenv import load_dotenv
from os import listdir
from collections import Counter
from tqdm.contrib.concurrent import process_map
from pathlib import Path
from structures import Letter, Category

logging.basicConfig(
    filename='classifier.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("main")

load_dotenv()

global_env = Path.home() / ".email-classifier.env"
if global_env.exists():
    load_dotenv(dotenv_path=global_env)

DEFAULT_CATEGORIES = [
    Category("spam", ("casino", "win", "discount", "скидк", "выигрыш", "реклама", "казино")),
    Category("alerts", ("alert", "grafana", "zabbix", "prometheus", "noreply", "daemon")),
    Category("urgent", ("urgent", "срочно", "критичн", "падает", "ошибка 500", "инцидент", "недоступен")),
    Category("newsletters", ("дайджест", "newsletter", "рассылка", "новост")),
    Category("hr_documents", ("отпуск", "больничный", "инструкция", "согласование", "договор", "заявление"))
]


def get_keywords(cat_name: str) -> tuple[str, ...]:
    kw_str = os.getenv(f"{cat_name.upper()}_KEYWORDS")
    if kw_str:
        return tuple(kw.strip().lower() for kw in kw_str.split(',') if kw.strip())
    default = next((c for c in DEFAULT_CATEGORIES if c.name == cat_name), None)
    return default.keywords if default else ()


def load_categories() -> list[Category]:
    categories_str = os.getenv("CATEGORIES")
    if not categories_str:
        return DEFAULT_CATEGORIES

    category_names = [c.strip() for c in categories_str.split(',') if c.strip()]
    return [Category(name, get_keywords(name)) for name in category_names]


ACTIVE_CATEGORIES = load_categories()

CATEGORY_NAMES = [cat.name for cat in ACTIVE_CATEGORIES] + ["unknown", "errors"]


def setup_directories(processed_dir):
    if not processed_dir.exists():
        processed_dir.mkdir()
    for cat in CATEGORY_NAMES:
        (processed_dir / cat).mkdir(exist_ok=True)


def classify_letter(letter: Letter) -> str:
    subject = (letter.subject or "").lower()
    text = (letter.text or "").lower()
    sender = (letter.sent_from_email or "").lower()

    search_text = f"{subject} {text} {sender}"

    for category in ACTIVE_CATEGORIES:
        if any(keyword in search_text for keyword in category.keywords):
            return category.name

    return "unknown"


def check_empty(file_path: Path, content: list[str]) -> bool:
    if not content:
        logger.warning(f"Empty file: {file_path}")
        logger.info(f"Classified {file_path} as errors")
        return True

    return False


def check_letter(file_path: Path, letter: Letter) -> bool:
    if not letter.text or not letter.sent_from_email:
        logger.warning(f"Could not extract meaningful data from: {file_path}")
        logger.info(f"Classified {file_path} as errors")
        return True
    return False


def classify_file(file_path: Path) -> str:
    try:
        if not isinstance(file_path, Path):
            raise TypeError(f"{file_path} is not a Path")

        if file_path.suffix != ".txt":
            raise ValueError(f"Invalid file format: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()

        if check_empty(file_path, content) or check_letter(file_path, letter := Letter(content)):
            return "errors"

        category = classify_letter(letter)
        logger.info(f"Classified {file_path} as {category}")
        return category

    except (TypeError, ValueError, IndexError) as e:
        logger.warning(str(e))

    except Exception as e:
        logger.warning(f"Error occurred {e} during {file_path} parsing.")

    logger.info(f"Classified {file_path} as errors")
    return "errors"


def move_file(processed_dir: Path, file_path: Path, category: str) -> None:
    destination = processed_dir / category / file_path.name
    try:
        shutil.move(str(file_path), str(destination))
    except Exception as e:
        logger.error(f"Failed to move file {file_path} to {destination}: {e}")


def main(input_dir: Path, output_dir: Path, n_jobs: int) -> None:
    if not input_dir.exists():
        logger.error(f"Directory {input_dir} does not exist.")
        print(f"Directory {input_dir} does not exist.")
        return

    setup_directories(output_dir)

    files = listdir(input_dir)

    logger.info("Starting email classification.")

    file_paths = [input_dir / file_path for file_path in files]

    categories = process_map(classify_file, file_paths, max_workers=n_jobs,
                             desc="Classifying letters")

    stats = Counter(categories)

    process_map(move_file, [output_dir for _ in file_paths], file_paths, categories, max_workers=n_jobs,
                desc="Moving to folders")

    logger.info("Classification finished.")

    with open("stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

    print("Classification completed successfully.")
    print("Statistics:")
    for cat, count in stats.items():
        print(f"  {cat}: {count}")


def run_cli():
    parser = argparse.ArgumentParser(description="A simple CLI tool for email classification.")
    parser.add_argument("-i", "--input", type=str, default="inbox", help="Input folder")
    parser.add_argument("-o", "--output", type=str, default="processed", help="Output folder")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="Amount of CPU cores to use")

    args = parser.parse_args()

    input_dir = Path(args.input)
    processed_dir = Path(args.output)

    main(input_dir, processed_dir, args.jobs)


if __name__ == "__main__":
    run_cli()

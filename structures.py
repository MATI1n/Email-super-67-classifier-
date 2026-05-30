import re
import dateparser
from typing import List, Optional
from email.utils import parseaddr
from typing import NamedTuple

class Category(NamedTuple):
    name: str
    keywords: tuple[str, ...]


class Letter:
    __HEADER_PATTERN = re.compile(
        r'\b(?:From|От кого|Ot kogo)[:\s]*(?P<from>.*)|'
        r'\b(?:To|Кому|Komu)[:\s]*(?P<to>.*)|'
        r'\b(?:Subject|Тема|Tema)[:\s]*(?P<subject>.*)|'
        r'\b(?:Date|Дата|Data)[:\s]*(?P<date>.*)',
        re.IGNORECASE
    )

    def __init__(self, text_lines: List[str]):
        self.__raw_text = text_lines

        self._sent_from_name: Optional[str] = None
        self._sent_from_email: Optional[str] = None

        self._sent_to: Optional[str] = None
        self._subject: Optional[str] = None
        self._date = None
        self._text: str = ""

        self.__process_raw_text()

    def __process_raw_text(self) -> None:
        text_lines_accumulator = []

        for line in self.__raw_text:
            match = self.__HEADER_PATTERN.search(line)

            if not match:
                text_lines_accumulator.append(line)
                continue

            groups = match.groupdict()

            if groups['from'] and not self._sent_from_email:
                raw_from = groups['from'].strip()
                name, email = parseaddr(raw_from)

                self._sent_from_name = name if name else None
                self._sent_from_email = email if email else raw_from

            elif groups['to'] and not self._sent_to:
                self._sent_to = groups['to'].strip()
            elif groups['subject'] and not self._subject:
                self._subject = groups['subject'].strip()
            elif groups['date'] and not self._date:
                raw_date = groups['date'].strip()
                self._date = dateparser.parse(raw_date, settings={'DATE_ORDER': 'DMY'})
            else:
                text_lines_accumulator.append(line)

        self._text = "\n".join([line for line in text_lines_accumulator if line != "\n"])

    @property
    def sent_from_name(self) -> Optional[str]:
        return self._sent_from_name

    @property
    def sent_from_email(self) -> Optional[str]:
        return self._sent_from_email

    @property
    def sent_to(self) -> Optional[str]:
        return self._sent_to

    @property
    def subject(self) -> Optional[str]:
        return self._subject

    @property
    def date(self):
        return self._date

    @property
    def text(self) -> str:
        return self._text

    def __str__(self) -> str:
        return (
            f'{{"From Name": "{self.sent_from_name}", '
            f'"From Email": "{self.sent_from_email}", '
            f'"To": "{self.sent_to}", '
            f'"Subject": "{self.subject}", '
            f'"Date": "{self.date}", '
            f'"Text_Lines_Count": {len(self.text.splitlines())}}}'
        )

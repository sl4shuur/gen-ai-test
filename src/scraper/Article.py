from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    """Article data structure"""
    title: str
    url: str
    content: str
    published_date: datetime
    images: list[str]
    author: str = ""
    category: str = ""

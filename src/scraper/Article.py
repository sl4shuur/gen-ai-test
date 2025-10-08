from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
from pathlib import Path


@dataclass
class Article:
    """Data structure for a scraped article"""
    
    # Basic metadata
    url: str
    title: str
    published_date: datetime
    author: str = "Unknown"
    
    # Content
    content: str = ""
    summary: str = ""
    
    # Media
    images: list[str] = field(default_factory=list)
    image_descriptions: list[str] = field(default_factory=list)
    
    # For RAG
    embeddings: list[float] | None = None
    
    # Timestamps
    scraped_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['published_date'] = self.published_date.isoformat()
        data['scraped_at'] = self.scraped_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Article':
        """Create Article from dictionary"""
        # Convert ISO strings back to datetime
        if isinstance(data.get('published_date'), str):
            data['published_date'] = datetime.fromisoformat(data['published_date'])
        if isinstance(data.get('scraped_at'), str):
            data['scraped_at'] = datetime.fromisoformat(data['scraped_at'])
        return cls(**data)
    
    def save_to_json(self, output_dir: Path) -> Path:
        """Save article to JSON file"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename from URL
        filename = self.url.split('/')[-1] or 'article'
        filepath = output_dir / f"{filename}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        
        return filepath
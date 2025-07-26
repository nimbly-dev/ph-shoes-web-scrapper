# base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from uuid import uuid4

@dataclass
class BaseShoe:
    """
    Canonical shoe record. Every extractor should emit this shape.
    `extra` is nullable and holds any site-specific metadata.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    subTitle: Optional[str] = None
    url: str = ""
    image: Optional[str] = None
    price_sale: float = 0.0
    price_original: Optional[float] = None
    gender: List[str] = field(default_factory=list)
    age_group: Optional[str] = "adult"
    brand: str = "unknown"
    extra: Optional[Dict[str, Any]] = None


class BaseExtractor(ABC):
    """
    Abstract base for all brand-specific extractors.
    Implement `extract()` to return a list of BaseShoe instances.
    """

    @abstractmethod
    def extract(self) -> List[BaseShoe]:
        """
        Fetch and normalize data from the source, returning
        a list of BaseShoe dataclass objects.
        """
        pass

from abc import ABC, abstractmethod
from typing import List

class Translator(ABC):
    @abstractmethod
    def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
        ...

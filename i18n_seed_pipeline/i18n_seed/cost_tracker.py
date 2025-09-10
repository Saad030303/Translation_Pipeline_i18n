from dataclasses import dataclass

@dataclass
class CostTracker:
    cost_per_million: float = 15.0
    prompt_chars: int = 0
    completion_chars: int = 0

    def add(self, prompt_chars: int, completion_chars: int) -> None:
        self.prompt_chars += prompt_chars
        self.completion_chars += completion_chars

    @property
    def total_chars(self) -> int:
        return self.prompt_chars + self.completion_chars

    @property
    def est_cost_usd(self) -> float:
        return (self.total_chars / 1_000_000.0) * self.cost_per_million

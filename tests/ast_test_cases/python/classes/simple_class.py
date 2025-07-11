"""Test case: Simple Python class for AST parsing."""


class Calculator:
    """A simple calculator class."""

    def __init__(self, initial_value: float = 0):
        """Initialize calculator with a starting value."""
        self.value = initial_value
        self.history: list = []

    def add(self, amount: float) -> float:
        """Add amount to current value."""
        self.value += amount
        self.history.append(f"Added {amount}")
        return self.value

    def subtract(self, amount: float) -> float:
        """Subtract amount from current value."""
        self.value -= amount
        self.history.append(f"Subtracted {amount}")
        return self.value

    def reset(self) -> None:
        """Reset calculator to zero."""
        self.value = 0
        self.history.clear()

    def get_history(self) -> list:
        """Get operation history."""
        return self.history.copy()

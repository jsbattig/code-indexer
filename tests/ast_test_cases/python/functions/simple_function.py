"""Test case: Simple Python functions for AST parsing."""


def greet(name: str) -> str:
    """Greet a person by name."""
    return f"Hello, {name}!"


def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    result = a + b
    return result


def process_list(items: list) -> list:
    """Process a list of items."""
    processed = []
    for item in items:
        if isinstance(item, str):
            processed.append(item.upper())
        else:
            processed.append(str(item))
    return processed

"""
Test Project 1 - Simple Python Calculator
A basic calculator with add, subtract, multiply, and divide functions.
"""


def add(a, b):
    """Add two numbers together."""
    return a + b


def subtract(a, b):
    """Subtract second number from first."""
    return a - b


def multiply(a, b):
    """Multiply two numbers."""
    return a * b


def divide(a, b):
    """Divide first number by second."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def calculator(operation, a, b):
    """Main calculator function."""
    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }

    if operation not in operations:
        raise ValueError(f"Unknown operation: {operation}")

    return operations[operation](a, b)


def main():
    """Example usage of the calculator."""
    print("Calculator Demo")
    print(f"5 + 3 = {calculator('add', 5, 3)}")
    print(f"10 - 4 = {calculator('subtract', 10, 4)}")
    print(f"7 * 6 = {calculator('multiply', 7, 6)}")
    print(f"15 / 3 = {calculator('divide', 15, 3)}")


if __name__ == "__main__":
    main()

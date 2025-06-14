"""
Utility functions for Test Project 1
Mathematical helpers and formatting functions.
"""

import math

def factorial(n):
    """Calculate factorial of n."""
    if n < 0:
        raise ValueError("Factorial not defined for negative numbers")
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)

def power(base, exponent):
    """Calculate base raised to the power of exponent."""
    return base ** exponent

def square_root(n):
    """Calculate square root of n."""
    if n < 0:
        raise ValueError("Square root not defined for negative numbers")
    return math.sqrt(n)

def is_prime(n):
    """Check if a number is prime."""
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def format_result(operation, a, b, result):
    """Format calculation result for display."""
    return f"{a} {operation} {b} = {result}"
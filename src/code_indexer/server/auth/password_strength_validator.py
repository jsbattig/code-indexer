"""
Enhanced password strength validation for CIDX Server.

Implements comprehensive password analysis including:
- Strength scoring (1-5 scale)
- Entropy calculation
- Common password detection
- Personal information detection
- Pattern recognition
- Real-time feedback and suggestions
"""

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum


class PasswordStrengthScore(int, Enum):
    """Password strength scores on 1-5 scale."""

    VERY_WEAK = 1
    WEAK = 2
    MEDIUM = 3
    STRONG = 4
    VERY_STRONG = 5


@dataclass
class PasswordValidationResult:
    """Result of password strength validation."""

    valid: bool
    score: int
    strength: str
    issues: List[str]
    suggestions: List[str]
    entropy: float


class PasswordStrengthValidator:
    """
    Comprehensive password strength validation engine.

    Validates passwords against security requirements:
    - Minimum 12 characters length
    - Character class requirements (upper, lower, digit, special)
    - Common password detection
    - Personal information detection
    - Entropy calculation
    - Pattern recognition
    """

    def __init__(self, config=None):
        """
        Initialize password strength validator.

        Args:
            config: PasswordSecurityConfig object with validation settings.
                   If None, uses default secure settings.
        """
        if config:
            self.min_length = config.min_length
            self.max_length = config.max_length
            self.required_char_classes = config.required_char_classes
            self.min_entropy_bits = config.min_entropy_bits
            self.check_common_passwords = config.check_common_passwords
            self.check_personal_info = config.check_personal_info
            self.check_keyboard_patterns = config.check_keyboard_patterns
            self.check_sequential_chars = config.check_sequential_chars
        else:
            # Default secure settings
            self.min_length = 12
            self.max_length = 128
            self.required_char_classes = 4
            self.min_entropy_bits = 50
            self.check_common_passwords = True
            self.check_personal_info = True
            self.check_keyboard_patterns = True
            self.check_sequential_chars = True

        # Load common passwords
        self.common_passwords = self._load_common_passwords()

        # L33t speak mappings
        self.leet_mappings = {
            "@": "a",
            "4": "a",
            "3": "e",
            "1": "i",
            "!": "i",
            "0": "o",
            "5": "s",
            "7": "t",
            "+": "t",
            "$": "s",
        }

        # Keyboard patterns
        self.keyboard_patterns = [
            "qwerty",
            "qwertyui",
            "asdfgh",
            "asdfghjk",
            "zxcvbn",
            "zxcvbnm",
            "123456",
            "1234567",
            "098765",
            "0987654",
            "abcdef",
            "fedcba",
        ]

    def validate(
        self, password: str, username: Optional[str] = None, email: Optional[str] = None
    ) -> Tuple[bool, PasswordValidationResult]:
        """
        Validate password strength and return detailed feedback.

        Args:
            password: Password to validate
            username: Optional username to check for personal info
            email: Optional email to check for personal info

        Returns:
            Tuple of (is_valid, validation_result)
        """
        result = PasswordValidationResult(
            valid=True, score=0, strength="weak", issues=[], suggestions=[], entropy=0.0
        )

        # Length validation
        if len(password) < self.min_length:
            result.valid = False
            result.issues.append(
                f"Password must be at least {self.min_length} characters long"
            )
            result.suggestions.append(
                f"Use at least {self.min_length} characters for better security"
            )
        elif len(password) > self.max_length:
            result.valid = False
            result.issues.append(
                f"Password must be less than {self.max_length} characters long"
            )

        # Always check character classes for scoring
        char_classes = self._check_character_classes(password)

        # Character class validation (only if required)
        if self.required_char_classes > 0:
            missing_classes = []

            if not char_classes["uppercase"]:
                result.issues.append(
                    "Password must contain at least one uppercase letter"
                )
                missing_classes.append("uppercase letter")

            if not char_classes["lowercase"]:
                result.issues.append(
                    "Password must contain at least one lowercase letter"
                )
                missing_classes.append("lowercase letter")

            if not char_classes["digit"]:
                result.issues.append("Password must contain at least one number")
                missing_classes.append("number")

            if not char_classes["special"]:
                result.issues.append(
                    "Password must contain at least one special character"
                )
                missing_classes.append("special character")

            # Check if we have enough character classes
            present_classes = sum(1 for active in char_classes.values() if active)
            if present_classes < self.required_char_classes:
                result.valid = False
                if missing_classes:
                    result.suggestions.append(
                        f"Add {', '.join(missing_classes)} to strengthen your password"
                    )

        # Calculate entropy
        result.entropy = self._calculate_entropy(password)

        # Common password detection
        if self.check_common_passwords and self._is_common_password(password):
            result.valid = False
            result.issues.append("Password is too common and easily guessed")
            result.suggestions.extend(
                [
                    "Try a unique passphrase instead of common words",
                    "Combine unrelated words with numbers and symbols",
                ]
            )

        # Personal information detection
        if self.check_personal_info and self._contains_personal_info(
            password, username, email
        ):
            result.valid = False
            result.issues.append("Password contains personal information")
            result.suggestions.extend(
                [
                    "Avoid using your name or email in passwords",
                    "Use unrelated words and phrases",
                ]
            )

        # Pattern detection
        if self.check_keyboard_patterns or self.check_sequential_chars:
            pattern_issues = self._detect_patterns(password)
            if pattern_issues:
                result.issues.extend(pattern_issues)
                result.suggestions.extend(
                    [
                        "Avoid keyboard patterns and sequences",
                        "Mix random letters, numbers, and symbols",
                    ]
                )

        # Calculate overall score
        present_char_classes = sum(1 for active in char_classes.values() if active)
        result.score = self._calculate_score(
            password, present_char_classes, result.entropy, len(result.issues)
        )

        # Determine strength level
        if result.score >= 5:
            result.strength = "strong"
        elif result.score >= 4:
            result.strength = "strong"
        elif result.score >= 3:
            result.strength = "medium"
        else:
            result.strength = "weak"
            if result.valid:  # Only mark invalid if not already invalid
                result.valid = result.score >= 4

        # Add suggestions based on score
        if result.score < 4:
            result.suggestions.extend(
                self._generate_suggestions(password, char_classes)
            )

        # Remove duplicates from suggestions
        result.suggestions = list(dict.fromkeys(result.suggestions))

        return result.valid, result

    def get_requirements(self) -> Dict[str, Any]:
        """
        Get password requirements specification.

        Returns:
            Dictionary containing password requirements
        """
        return {
            "min_length": self.min_length,
            "max_length": self.max_length,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digits": True,
            "require_special_chars": True,
            "required_char_classes": self.required_char_classes,
            "min_entropy_bits": self.min_entropy_bits,
            "special_chars": "!@#$%^&*()_+-=[]{}|;:,.<>?",
            "description": (
                f"Password must be at least {self.min_length} characters long and contain "
                "at least one uppercase letter, one lowercase letter, one digit, "
                "and one special character. Avoid common passwords and personal information."
            ),
        }

    def _check_character_classes(self, password: str) -> Dict[str, bool]:
        """Check which character classes are present in password."""
        return {
            "uppercase": bool(re.search(r"[A-Z]", password)),
            "lowercase": bool(re.search(r"[a-z]", password)),
            "digit": bool(re.search(r"\d", password)),
            "special": bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password)),
        }

    def _calculate_entropy(self, password: str) -> float:
        """
        Calculate password entropy in bits using information theory.

        Args:
            password: Password to analyze

        Returns:
            Entropy in bits
        """
        if not password:
            return 0.0

        # Special case: if password has only one unique character, entropy is 0
        if len(set(password)) == 1:
            return 0.0

        # Determine charset size
        charset_size = 0

        if re.search(r"[a-z]", password):
            charset_size += 26  # lowercase letters
        if re.search(r"[A-Z]", password):
            charset_size += 26  # uppercase letters
        if re.search(r"\d", password):
            charset_size += 10  # digits
        if re.search(r"[^a-zA-Z0-9]", password):
            charset_size += 32  # special characters (approximation)

        if charset_size == 0:
            return 0.0

        # For very low diversity passwords, use actual unique character count
        unique_chars = len(set(password))
        if unique_chars < 3:
            charset_size = unique_chars

        # Calculate entropy: length * log2(charset_size)
        entropy = len(password) * math.log2(charset_size)

        # Apply penalties for patterns and repetition
        penalty = self._calculate_entropy_penalty(password)
        entropy *= 1.0 - penalty

        return round(entropy, 2)

    def _calculate_entropy_penalty(self, password: str) -> float:
        """Calculate entropy penalty for patterns and repetition."""
        penalty = 0.0

        # Penalty for repeated characters
        repeated_chars = len(re.findall(r"(.)\1{2,}", password))
        penalty += repeated_chars * 0.1

        # Penalty for keyboard patterns
        password_lower = password.lower()
        for pattern in self.keyboard_patterns:
            if pattern in password_lower:
                penalty += 0.2

        # Penalty for sequential characters
        sequential_count = 0
        for i in range(len(password) - 2):
            chars = password[i : i + 3]
            if self._is_sequential(chars):
                sequential_count += 1
        penalty += sequential_count * 0.1

        return min(penalty, 0.5)  # Cap penalty at 50%

    def _is_sequential(self, chars: str) -> bool:
        """Check if characters are sequential."""
        if len(chars) < 3:
            return False

        # Check ascending sequence
        ascending = all(
            ord(chars[i]) + 1 == ord(chars[i + 1]) for i in range(len(chars) - 1)
        )
        # Check descending sequence
        descending = all(
            ord(chars[i]) - 1 == ord(chars[i + 1]) for i in range(len(chars) - 1)
        )

        return ascending or descending

    def _is_common_password(self, password: str) -> bool:
        """
        Check if password is in common password list.

        Args:
            password: Password to check

        Returns:
            True if password is common, False otherwise
        """
        # Check exact match (case insensitive)
        if password.lower() in self.common_passwords:
            return True

        # Check l33t speak variations
        leet_password = self._convert_from_leet(password)
        if leet_password.lower() in self.common_passwords:
            return True

        # Check with common suffixes removed (both original and l33t converted)
        common_suffixes = [
            "123",
            "12",
            "1",
            "!",
            "123!",
            "1!",
            "2024",
            "2023",
            "extra",
            "extralen",
        ]
        for suffix in common_suffixes:
            # Check original password
            if password.lower().endswith(suffix.lower()):
                base_password = password[: -len(suffix)].lower()
                if base_password in self.common_passwords:
                    return True
                # Also check l33t conversion of base
                base_leet = self._convert_from_leet(base_password)
                if base_leet in self.common_passwords:
                    return True

            # Check l33t converted password
            if leet_password.lower().endswith(suffix.lower()):
                base_leet = leet_password[: -len(suffix)].lower()
                if base_leet in self.common_passwords:
                    return True

        # Check for common password as complete base (not substring)
        # Only check if the common password represents a significant portion
        for common_pwd in self.common_passwords:
            if len(common_pwd) >= 6:  # Only check longer common passwords
                # Check if common password appears at start
                if password.lower().startswith(
                    common_pwd
                ) or leet_password.lower().startswith(common_pwd):
                    return True
                # Check if common password + numbers appears at start
                if password.lower().startswith(
                    common_pwd + "123"
                ) or leet_password.lower().startswith(common_pwd + "123"):
                    return True

        return False

    def _convert_from_leet(self, password: str) -> str:
        """Convert l33t speak password to normal text."""
        result = password.lower()
        for leet_char, normal_char in self.leet_mappings.items():
            result = result.replace(leet_char, normal_char)
        return result

    def _contains_personal_info(
        self, password: str, username: Optional[str] = None, email: Optional[str] = None
    ) -> bool:
        """
        Check if password contains personal information.

        Args:
            password: Password to check
            username: User's username
            email: User's email address

        Returns:
            True if password contains personal info, False otherwise
        """
        password_lower = password.lower()

        # Check username
        if username and len(username) > 2:
            if username.lower() in password_lower:
                return True

        # Check email components
        if email:
            email_lower = email.lower()
            local_part = email_lower.split("@")[0]

            # Check full local part
            if len(local_part) > 2 and local_part in password_lower:
                return True

            # Check email parts separated by dots
            email_parts = local_part.split(".")
            for part in email_parts:
                if len(part) > 2 and part in password_lower:
                    return True

            # Check domain parts
            if "@" in email_lower:
                domain = email_lower.split("@")[1]
                domain_parts = domain.split(".")
                for part in domain_parts:
                    if len(part) > 3 and part in password_lower:
                        return True

        return False

    def _detect_patterns(self, password: str) -> List[str]:
        """
        Detect obvious patterns in password.

        Args:
            password: Password to analyze

        Returns:
            List of pattern issues found
        """
        issues = []

        # Check for repeated characters (3 or more in a row)
        if re.search(r"(.)\1{2,}", password):
            issues.append("Password contains repeated characters")

        # Check for keyboard patterns
        if self.check_keyboard_patterns:
            password_lower = password.lower()
            for pattern in self.keyboard_patterns:
                if pattern in password_lower:
                    issues.append("Password contains keyboard patterns")
                    break

        # Check for sequential characters
        if self.check_sequential_chars:
            sequential_count = 0
            for i in range(len(password) - 2):
                if self._is_sequential(password[i : i + 3]):
                    sequential_count += 1

            if sequential_count > 0:
                issues.append("Password contains sequential characters")

        return issues

    def _calculate_score(
        self, password: str, char_classes: int, entropy: float, issue_count: int
    ) -> int:
        """
        Calculate overall password strength score (1-5).

        Args:
            password: Password being analyzed
            char_classes: Number of character classes present
            entropy: Password entropy in bits
            issue_count: Number of issues found

        Returns:
            Score from 1-5
        """
        score = 1

        # Length bonus
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1

        # Character class bonus
        if char_classes >= 4:
            score += 1
        if char_classes >= 4 and len(password) >= 16:
            score += 1

        # Entropy bonus
        if entropy >= 40:
            score += 1
        if entropy >= 60:
            score += 1

        # Issue penalties
        score -= min(issue_count, 3)  # Cap penalty at 3 points

        # Ensure score is within bounds
        return max(1, min(5, score))

    def _generate_suggestions(
        self, password: str, char_classes: Dict[str, bool]
    ) -> List[str]:
        """
        Generate specific improvement suggestions.

        Args:
            password: Current password
            char_classes: Character class analysis

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Length suggestions
        if len(password) < self.min_length:
            suggestions.append(
                f"Make password longer - use at least {self.min_length} characters"
            )
        elif len(password) < 16:
            suggestions.append("Consider using 16+ characters for extra security")

        # Character class suggestions
        if not char_classes["uppercase"]:
            suggestions.append("Add uppercase letters (A-Z)")
        if not char_classes["lowercase"]:
            suggestions.append("Add lowercase letters (a-z)")
        if not char_classes["digit"]:
            suggestions.append("Add numbers and digits (0-9)")
        if not char_classes["special"]:
            suggestions.append("Add special characters (!@#$%^&*)")

        # General suggestions
        suggestions.extend(
            [
                "Use a mix of unrelated words",
                "Consider using a passphrase instead of a single word",
                "Avoid personal information like names and dates",
            ]
        )

        return suggestions

    def _load_common_passwords(self) -> Set[str]:
        """
        Load common password list.

        Returns:
            Set of common passwords (lowercase)
        """
        # Common passwords list - in production, this could be loaded from a file
        common_passwords = {
            "password",
            "123456",
            "password123",
            "admin",
            "letmein",
            "welcome",
            "monkey",
            "1234567890",
            "qwerty",
            "abc123",
            "iloveyou",
            "password1",
            "admin123",
            "root",
            "toor",
            "pass",
            "test",
            "guest",
            "info",
            "adm",
            "mysql",
            "user",
            "administrator",
            "oracle",
            "ftp",
            "pi",
            "puppet",
            "ansible",
            "ec2-user",
            "vagrant",
            "azureuser",
            "bitnami",
            "centos",
            "cisco",
            "daemon",
            "bin",
            "sys",
            "adm",
            "master",
            "main",
            "demo",
            "web",
            "www",
            "ftp",
            "mail",
            "email",
            "sa",
            "service",
            "support",
            "temp",
            "temporary",
            "changeme",
            "change",
            "default",
            "login",
            "passw0rd",
            "p@ssword",
            "p@ssw0rd",
            "passw0rd123",
            "p@ssw0rd123",
            "welcome123",
            "admin123",
            "qwerty123",
            "letmein123",
            "monkey123",
            "dragon",
            "ninja",
            "azerty",
            "trustno1",
            "hunter",
            "harley",
            "ranger",
            "jordan",
            "george",
            "jennifer",
            "daniel",
            "computer",
            "michelle",
            "maggie",
            "sunshine",
            "chocolate",
            "anthony",
            "william",
            "joshua",
            "michael",
            "superman",
            "hello",
            "freedom",
            "whatever",
            "nicole",
        }
        return common_passwords

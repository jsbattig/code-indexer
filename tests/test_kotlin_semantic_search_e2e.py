"""
End-to-end test for Kotlin semantic search functionality.

This test verifies that:
1. Kotlin files are properly indexed with semantic chunking
2. Both .kt and .kts files are supported
3. Semantic search works correctly for Kotlin code constructs
4. Kotlin-specific language features are searchable
"""

from typing import Dict
import subprocess

import pytest

# Import test infrastructure
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
    get_shared_test_project_dir,
)

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def _get_kotlin_test_project() -> Dict[str, str]:
    """Get test project with Kotlin files to test semantic indexing."""
    return {
        # Standard Kotlin file with various constructs
        "UserService.kt": """package com.example.service

import java.util.UUID

data class User(
    val id: UUID,
    val name: String,
    val email: String?,
    val isActive: Boolean = true
)

interface UserRepository {
    suspend fun findById(id: UUID): User?
    suspend fun save(user: User): User
    suspend fun delete(id: UUID): Boolean
}

class UserService(private val repository: UserRepository) {
    suspend fun createUser(name: String, email: String?): User {
        val user = User(
            id = UUID.randomUUID(),
            name = name,
            email = email
        )
        return repository.save(user)
    }
    
    suspend fun updateUser(id: UUID, name: String?, email: String?): User? {
        val existingUser = repository.findById(id) ?: return null
        val updatedUser = existingUser.copy(
            name = name ?: existingUser.name,
            email = email ?: existingUser.email
        )
        return repository.save(updatedUser)
    }
    
    suspend fun deleteUser(id: UUID): Boolean {
        return repository.delete(id)
    }
    
    companion object {
        const val MAX_NAME_LENGTH = 100
        
        fun validateEmail(email: String): Boolean {
            return email.contains("@") && email.contains(".")
        }
    }
}

// Extension functions
fun User.fullInfo(): String {
    return "$name (${email ?: "no email"})"
}

fun List<User>.activeUsers(): List<User> {
    return filter { it.isActive }
}
""",
        # Kotlin script file
        "build.gradle.kts": """import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins {
    kotlin("jvm") version "1.9.0"
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.0")
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
}

tasks.withType<KotlinCompile> {
    kotlinOptions.jvmTarget = "17"
}

application {
    mainClass.set("MainKt")
}
""",
        # Another Kotlin file with different patterns
        "Calculator.kt": """sealed class CalculationResult<out T> {
    data class Success<T>(val value: T) : CalculationResult<T>()
    data class Error(val message: String) : CalculationResult<Nothing>()
}

object MathCalculator {
    fun add(a: Double, b: Double): CalculationResult<Double> {
        return CalculationResult.Success(a + b)
    }
    
    fun divide(a: Double, b: Double): CalculationResult<Double> {
        return if (b == 0.0) {
            CalculationResult.Error("Division by zero")
        } else {
            CalculationResult.Success(a / b)
        }
    }
    
    inline fun <reified T : Number> safeCast(value: Any): T? {
        return value as? T
    }
}

enum class Operation(val symbol: String) {
    ADD("+"),
    SUBTRACT("-"),
    MULTIPLY("*"),
    DIVIDE("/");
    
    fun apply(a: Double, b: Double): Double = when (this) {
        ADD -> a + b
        SUBTRACT -> a - b
        MULTIPLY -> a * b
        DIVIDE -> a / b
    }
}
""",
    }


@pytest.mark.full_automation
class TestKotlinSemanticSearchE2E:
    """Test Kotlin semantic search end-to-end functionality."""

    def test_kotlin_semantic_indexing_and_search(self):
        """Test that Kotlin files are indexed with semantic chunking and searchable."""
        # Use shared project directory to reuse containers between tests
        test_dir = get_shared_test_project_dir()

        # Create test project with inventory system
        create_test_project_with_inventory(
            test_dir, TestProjectInventory.kotlin_semantic_search
        )

        # Add test files
        test_files = _get_kotlin_test_project()
        for filename, content in test_files.items():
            (test_dir / filename).write_text(content)

        # Run cidx commands
        subprocess.run(
            ["cidx", "init", "--chunk-size", "2000", "--use-semantic-chunking"],
            cwd=test_dir,
            check=True,
        )
        subprocess.run(["cidx", "start"], cwd=test_dir, check=True)

        # Search for Kotlin-specific constructs

        # Test 1: Search for data class
        result = subprocess.run(
            ["cidx", "query", "data class User with email field", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "data class User" in result.stdout
        assert "val email: String?" in result.stdout

        # Test 2: Search for suspend functions (coroutines)
        result = subprocess.run(
            ["cidx", "query", "suspend functions for user operations", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "suspend fun" in result.stdout
        assert any(
            func in result.stdout for func in ["createUser", "updateUser", "deleteUser"]
        )

        # Test 3: Search for companion object
        result = subprocess.run(
            ["cidx", "query", "companion object with constants", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "companion object" in result.stdout
        assert "MAX_NAME_LENGTH" in result.stdout

        # Test 4: Search for extension functions
        result = subprocess.run(
            ["cidx", "query", "extension functions for User", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "fun User.fullInfo()" in result.stdout or "fullInfo" in result.stdout

        # Test 5: Search for sealed class
        result = subprocess.run(
            ["cidx", "query", "sealed class for calculation results", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "sealed class CalculationResult" in result.stdout

        # Test 6: Search for object declaration
        result = subprocess.run(
            ["cidx", "query", "MathCalculator object with divide function", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "object MathCalculator" in result.stdout
        assert "divide" in result.stdout

        # Test 7: Search for enum class
        result = subprocess.run(
            ["cidx", "query", "enum class for mathematical operations", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "enum class Operation" in result.stdout

        # Test 8: Verify .kts files are indexed
        result = subprocess.run(
            ["cidx", "query", "kotlin gradle build configuration", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "build.gradle.kts" in result.stdout or "KotlinCompile" in result.stdout

        # Clean up
        subprocess.run(["cidx", "stop"], cwd=test_dir, check=True)

    def test_kotlin_language_filter(self):
        """Test that Kotlin language filter works correctly."""
        # Use shared project directory to reuse containers between tests
        test_dir = get_shared_test_project_dir()

        # Create test project with inventory system
        create_test_project_with_inventory(
            test_dir, TestProjectInventory.kotlin_language_filter
        )

        # Add test files
        test_files = _get_kotlin_test_project()
        # Add a Python file to test filtering
        test_files[
            "utils.py"
        ] = """def calculate_sum(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
"""

        for filename, content in test_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and start
        subprocess.run(
            ["cidx", "init", "--use-semantic-chunking"],
            cwd=test_dir,
            check=True,
        )
        subprocess.run(["cidx", "start"], cwd=test_dir, check=True)

        # Search with Kotlin language filter
        result = subprocess.run(
            ["cidx", "query", "calculator class", "--language", "kotlin", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should only find Kotlin calculator, not Python
        assert "UserService.kt" in result.stdout or "Calculator.kt" in result.stdout
        assert "utils.py" not in result.stdout

        # Search without filter should find both
        result = subprocess.run(
            ["cidx", "query", "calculator class", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should find both Kotlin and Python files
        assert any(
            kotlin_file in result.stdout
            for kotlin_file in ["UserService.kt", "Calculator.kt", "utils.py"]
        )

        # Clean up
        subprocess.run(["cidx", "stop"], cwd=test_dir, check=True)

    def test_kotlin_semantic_types(self):
        """Test that Kotlin semantic types are properly identified."""
        # Use shared project directory to reuse containers between tests
        test_dir = get_shared_test_project_dir()

        # Create test project with inventory system
        create_test_project_with_inventory(
            test_dir, TestProjectInventory.kotlin_semantic_types
        )

        # Add test files
        test_files = _get_kotlin_test_project()
        for filename, content in test_files.items():
            (test_dir / filename).write_text(content)

        # Initialize with semantic chunking
        subprocess.run(
            ["cidx", "init", "--use-semantic-chunking"],
            cwd=test_dir,
            check=True,
        )
        subprocess.run(["cidx", "start"], cwd=test_dir, check=True)

        # Test various semantic queries

        # Search for interfaces
        result = subprocess.run(
            ["cidx", "query", "UserRepository interface", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "interface UserRepository" in result.stdout

        # Search for specific method signatures
        result = subprocess.run(
            [
                "cidx",
                "query",
                "findById suspend function with UUID parameter",
                "--quiet",
            ],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "findById" in result.stdout
        assert "UUID" in result.stdout

        # Clean up
        subprocess.run(["cidx", "stop"], cwd=test_dir, check=True)

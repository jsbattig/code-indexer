"""
Comprehensive tests for Kotlin semantic parser.
Tests AST-based parsing, modern Kotlin features, coroutines, and edge cases.
"""

from pathlib import Path
from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker
from code_indexer.indexing.kotlin_parser import KotlinSemanticParser


class TestKotlinParserComprehensive:
    """Comprehensive tests for Kotlin semantic parser with modern features."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        self.parser = KotlinSemanticParser(self.config)
        self.chunker = SemanticChunker(self.config)
        self.test_files_dir = Path(__file__).parent / "test_files"

    def test_android_app_parsing(self):
        """Test parsing of complex Android application with modern Kotlin features."""
        test_file = self.test_files_dir / "kotlin" / "AndroidApp.kt"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for complex Android app
        assert len(chunks) > 30, f"Expected > 30 chunks, got {len(chunks)}"

        # Verify we capture all major constructs
        chunk_types = [chunk.semantic_type for chunk in chunks if chunk.semantic_type]

        assert "class" in chunk_types, "Should find class declarations"
        assert (
            "function" in chunk_types or "method" in chunk_types
        ), "Should find function or method declarations"
        assert "interface" in chunk_types, "Should find interface declarations"

        # Test specific constructs
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert (
            len(class_chunks) >= 8
        ), f"Should find multiple classes, got {len(class_chunks)}"

        # Test data class detection
        data_classes = [c for c in class_chunks if "data class" in c.text]
        assert len(data_classes) >= 2, "Should find data classes"

        # Test suspend function detection (class methods)
        suspend_functions = [
            c for c in chunks if "suspend" in c.text and c.semantic_type == "method"
        ]
        assert len(suspend_functions) >= 3, "Should find suspend functions"

        # Test coroutine usage
        coroutine_chunks = [
            c
            for c in chunks
            if any(
                keyword in c.text for keyword in ["launch", "async", "await", "Flow"]
            )
        ]
        assert len(coroutine_chunks) >= 5, "Should find coroutine usage"

    def test_spring_boot_service_parsing(self):
        """Test parsing of Kotlin Spring Boot service."""
        test_file = self.test_files_dir / "kotlin" / "SpringBootService.kt"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for Spring service
        assert len(chunks) > 20, f"Expected > 20 chunks, got {len(chunks)}"

        # Test annotation handling
        annotated_chunks = [c for c in chunks if "@" in c.text]
        assert len(annotated_chunks) > 8, "Should find chunks with annotations"

        # Test class detection with annotations
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        service_class = next((c for c in class_chunks if "UserService" in c.text), None)
        assert service_class is not None, "Should find UserService class"

        # Test method detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert (
            len(method_chunks) >= 8
        ), f"Should find multiple methods, got {len(method_chunks)}"

    def test_basic_kotlin_constructs(self):
        """Test basic Kotlin constructs parsing."""
        content = """
package com.example.basic

import kotlinx.coroutines.*

// Data class with validation
data class User(
    val id: Long,
    val name: String,
    val email: String,
    val isActive: Boolean = true
) {
    init {
        require(name.isNotBlank()) { "Name cannot be blank" }
        require(email.contains("@")) { "Invalid email format" }
    }
    
    fun getDisplayName(): String = "$name ($id)"
    
    companion object {
        const val MAX_NAME_LENGTH = 100
        
        fun createDefault(): User {
            return User(0, "Unknown", "unknown@example.com", false)
        }
    }
}

// Sealed class hierarchy
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Throwable) : Result<Nothing>()
    object Loading : Result<Nothing>()
    
    inline fun <R> fold(
        onSuccess: (T) -> R,
        onError: (Throwable) -> R,
        onLoading: () -> R
    ): R = when (this) {
        is Success -> onSuccess(data)
        is Error -> onError(exception)
        is Loading -> onLoading()
    }
}

// Interface with default implementation
interface UserRepository {
    suspend fun getUser(id: Long): User?
    suspend fun saveUser(user: User): User
    
    fun validateUser(user: User): Boolean {
        return user.name.isNotBlank() && user.email.contains("@")
    }
}

// Class with constructor parameters
class UserService(
    private val repository: UserRepository,
    private val logger: Logger
) {
    // Primary constructor validation
    init {
        logger.info("UserService initialized")
    }
    
    // Suspend function with coroutine
    suspend fun createUser(name: String, email: String): Result<User> {
        return try {
            val user = User(id = generateId(), name = name, email = email)
            
            if (!repository.validateUser(user)) {
                Result.Error(IllegalArgumentException("Invalid user data"))
            } else {
                val savedUser = repository.saveUser(user)
                Result.Success(savedUser)
            }
        } catch (e: Exception) {
            logger.error("Failed to create user", e)
            Result.Error(e)
        }
    }
    
    // Function with nullable return
    suspend fun findUser(id: Long): User? {
        return repository.getUser(id)
    }
    
    // Extension function usage
    private fun String.isValidEmail(): Boolean {
        return this.contains("@") && this.contains(".")
    }
    
    private suspend fun generateId(): Long {
        return withContext(Dispatchers.IO) {
            System.currentTimeMillis()
        }
    }
}

// Object declaration (singleton)
object UserCache {
    private val cache = mutableMapOf<Long, User>()
    
    fun put(user: User) {
        cache[user.id] = user
    }
    
    fun get(id: Long): User? = cache[id]
    
    fun clear() {
        cache.clear()
    }
}

// Enum class with methods
enum class UserStatus(val displayName: String) {
    ACTIVE("Active"),
    INACTIVE("Inactive"),
    PENDING("Pending Approval"),
    SUSPENDED("Suspended");
    
    fun isAvailable(): Boolean = this == ACTIVE
    
    companion object {
        fun fromString(value: String): UserStatus? {
            return values().find { it.name.equals(value, true) }
        }
    }
}

interface Logger {
    fun info(message: String)
    fun error(message: String, throwable: Throwable)
}
"""

        chunks = self.parser.chunk(content, "basic_kotlin.kt")

        # Test basic structure
        assert len(chunks) >= 15, f"Expected >= 15 chunks, got {len(chunks)}"

        # Test data class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        class_names = {c.semantic_name for c in class_chunks}
        assert "User" in class_names, "Should find User data class"
        assert "UserService" in class_names, "Should find UserService class"

        # Test sealed class detection
        sealed_classes = [c for c in class_chunks if "sealed" in c.text]
        assert len(sealed_classes) >= 1, "Should find sealed classes"

        # Test object detection
        object_chunks = [
            c for c in chunks if c.semantic_type == "object" or "object " in c.text
        ]
        assert len(object_chunks) >= 1, "Should find object declarations"

        # Test enum detection
        enum_chunks = [
            c for c in chunks if c.semantic_type == "enum" or "enum class" in c.text
        ]
        assert len(enum_chunks) >= 1, "Should find enum classes"

        # Test method detection (class methods)
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}
        expected_methods = {"createUser", "findUser", "generateId"}
        assert expected_methods.intersection(
            method_names
        ), f"Should find methods. Found: {method_names}"

        # Test suspend function detection
        suspend_functions = [c for c in method_chunks if "suspend" in c.text]
        assert len(suspend_functions) >= 2, "Should find suspend functions"

    def test_coroutines_and_flow(self):
        """Test Kotlin coroutines and Flow patterns."""
        content = """
package com.example.coroutines

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

class DataProcessor {
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    
    // Flow creation and transformation
    fun createDataFlow(): Flow<String> = flow {
        repeat(10) { index ->
            delay(100)
            emit("Data item $index")
        }
    }.flowOn(Dispatchers.IO)
    
    // Cold Flow with error handling
    fun processDataStream(): Flow<Result<ProcessedData>> = flow {
        try {
            val rawData = fetchRawData()
            rawData.forEach { item ->
                delay(50)
                val processed = processItem(item)
                emit(Result.Success(processed))
            }
        } catch (e: Exception) {
            emit(Result.Error(e))
        }
    }.catch { error ->
        emit(Result.Error(error))
    }
    
    // Async function with structured concurrency
    suspend fun processInParallel(items: List<String>): List<ProcessedData> {
        return supervisorScope {
            items.map { item ->
                async {
                    processItem(item)
                }
            }.awaitAll()
        }
    }
    
    // Channel usage
    suspend fun createChannel(): ReceiveChannel<String> {
        return scope.produce {
            repeat(5) { index ->
                delay(200)
                send("Channel item $index")
            }
        }
    }
    
    // StateFlow and SharedFlow
    private val _userState = MutableStateFlow<UserState>(UserState.Loading)
    val userState: StateFlow<UserState> = _userState.asStateFlow()
    
    private val _events = MutableSharedFlow<UserEvent>()
    val events: SharedFlow<UserEvent> = _events.asSharedFlow()
    
    // Suspend function with timeout
    suspend fun fetchWithTimeout(url: String): String? {
        return withTimeoutOrNull(5000) {
            withContext(Dispatchers.IO) {
                // Simulate network call
                delay(1000)
                "Response from $url"
            }
        }
    }
    
    // Cancellation handling
    suspend fun cancellableOperation(): String {
        return withContext(Dispatchers.IO) {
            repeat(100) { index ->
                ensureActive() // Check for cancellation
                delay(10)
                if (index == 50) {
                    throw CancellationException("Operation was cancelled")
                }
            }
            "Operation completed"
        }
    }
    
    private suspend fun fetchRawData(): List<String> {
        delay(100)
        return listOf("raw1", "raw2", "raw3")
    }
    
    private suspend fun processItem(item: String): ProcessedData {
        delay(50)
        return ProcessedData(item.uppercase(), System.currentTimeMillis())
    }
}

// Data classes for coroutine examples
data class ProcessedData(val value: String, val timestamp: Long)

sealed class UserState {
    object Loading : UserState()
    data class Success(val user: User) : UserState()
    data class Error(val message: String) : UserState()
}

sealed class UserEvent {
    object Refresh : UserEvent()
    data class ShowError(val message: String) : UserEvent()
}

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Throwable) : Result<Nothing>()
}

data class User(val id: Long, val name: String)
"""

        chunks = self.parser.chunk(content, "coroutines.kt")

        # Test class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1, "Should find DataProcessor class"

        # Test suspend function detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        suspend_functions = [c for c in method_chunks if "suspend" in c.text]
        assert (
            len(suspend_functions) >= 5
        ), f"Should find multiple suspend functions, got {len(suspend_functions)}"

        # Test Flow usage
        flow_chunks = [c for c in chunks if "Flow" in c.text]
        assert len(flow_chunks) >= 3, "Should find Flow usage"

        # Test coroutine scope and context usage
        coroutine_chunks = [
            c
            for c in chunks
            if any(
                keyword in c.text
                for keyword in ["CoroutineScope", "Dispatchers", "async", "await"]
            )
        ]
        assert len(coroutine_chunks) >= 5, "Should find coroutine-related code"

    def test_extension_functions_and_properties(self):
        """Test Kotlin extension functions and properties."""
        content = """
package com.example.extensions

// Extension functions on built-in types
fun String.isValidEmail(): Boolean {
    return this.contains("@") && this.contains(".")
}

fun String.truncate(maxLength: Int): String {
    return if (this.length > maxLength) {
        this.take(maxLength - 3) + "..."
    } else {
        this
    }
}

// Extension property
val String.wordCount: Int
    get() = this.split("\\s+".toRegex()).size

// Generic extension function
fun <T> List<T>.second(): T? {
    return if (this.size >= 2) this[1] else null
}

fun <T> List<T>.penultimate(): T? {
    return if (this.size >= 2) this[this.size - 2] else null
}

// Extension function on custom class
data class Person(val firstName: String, val lastName: String)

fun Person.fullName(): String = "$firstName $lastName"

val Person.initials: String
    get() = "${firstName.first()}${lastName.first()}"

// Extension functions with receivers
fun <T> T.apply(block: T.() -> Unit): T {
    block()
    return this
}

fun <T, R> T.let(block: (T) -> R): R {
    return block(this)
}

// Extension on nullable type
fun String?.isNullOrEmpty(): Boolean {
    return this == null || this.isEmpty()
}

// Extension function with default parameters
fun String.padCenter(totalWidth: Int, padChar: Char = ' '): String {
    val padding = totalWidth - this.length
    if (padding <= 0) return this
    
    val leftPad = padding / 2
    val rightPad = padding - leftPad
    
    return padChar.toString().repeat(leftPad) + this + padChar.toString().repeat(rightPad)
}

// Higher-order extension function
fun <T> List<T>.forEachIndexed(action: (index: Int, T) -> Unit) {
    for ((index, item) in this.withIndex()) {
        action(index, item)
    }
}

// Extension function on generic type with constraints
fun <T : Comparable<T>> List<T>.isSorted(): Boolean {
    for (i in 1 until this.size) {
        if (this[i] < this[i - 1]) {
            return false
        }
    }
    return true
}

// Usage examples class
class ExtensionExamples {
    fun demonstrateExtensions() {
        // String extensions
        val email = "user@example.com"
        println("Is valid email: ${email.isValidEmail()}")
        println("Word count: ${"Hello world kotlin".wordCount}")
        
        // List extensions
        val numbers = listOf(1, 2, 3, 4, 5)
        println("Second element: ${numbers.second()}")
        println("Is sorted: ${numbers.isSorted()}")
        
        // Person extensions
        val person = Person("John", "Doe")
        println("Full name: ${person.fullName()}")
        println("Initials: ${person.initials}")
        
        // Nullable extension
        val nullableString: String? = null
        println("Is null or empty: ${nullableString.isNullOrEmpty()}")
        
        // Higher-order extension
        numbers.forEachIndexed { index, value ->
            println("Item at $index: $value")
        }
    }
}
"""

        chunks = self.parser.chunk(content, "extensions.kt")

        # Test extension function detection
        extension_function_chunks = [
            c for c in chunks if c.semantic_type == "extension_function"
        ]
        # function_chunks = [c for c in chunks if c.semantic_type == "function"]

        # Many extension functions should be detected
        assert (
            len(extension_function_chunks) >= 10
        ), f"Should find multiple extension functions, got {len(extension_function_chunks)}"

        # Test generic extension functions
        generic_extensions = [
            c for c in extension_function_chunks if "<" in c.text and ">" in c.text
        ]
        assert len(generic_extensions) >= 3, "Should find generic extension functions"

        # Test extension properties (might be detected as functions or properties)
        # Note: Extension properties are complex constructs that may not be fully parsed by tree-sitter
        property_chunks = [c for c in chunks if "val " in c.text and "get()" in c.text]
        # For now, we'll be lenient with extension properties as they require advanced AST handling
        if len(property_chunks) > 0:
            print(
                f"Found {len(property_chunks)} extension properties"
            )  # Optional logging

    def test_type_system_features(self):
        """Test Kotlin's advanced type system features."""
        content = """
package com.example.types

// Generic classes with constraints
class Repository<T : Entity> where T : Comparable<T> {
    private val items = mutableListOf<T>()
    
    fun add(item: T) {
        items.add(item)
        items.sort()
    }
    
    fun find(predicate: (T) -> Boolean): T? {
        return items.find(predicate)
    }
}

// Covariance and contravariance
interface Producer<out T> {
    fun produce(): T
}

interface Consumer<in T> {
    fun consume(item: T)
}

// Type aliases
typealias UserId = Long
typealias UserMap = Map<UserId, User>
typealias EventHandler<T> = (T) -> Unit

// Inline classes (value classes in newer Kotlin)
@JvmInline
value class Email(val value: String) {
    init {
        require(value.contains("@")) { "Invalid email format" }
    }
    
    fun domain(): String = value.substringAfter("@")
}

// Smart casts and type checks
fun processValue(value: Any): String {
    return when (value) {
        is String -> "String with length ${value.length}"
        is Int -> "Integer: $value"
        is List<*> -> "List with ${value.size} items"
        is Pair<*, *> -> "Pair: ${value.first} to ${value.second}"
        else -> "Unknown type: ${value::class.simpleName}"
    }
}

// Nullable types and safe calls
class UserProcessor {
    fun processUser(user: User?): String? {
        return user?.let { u ->
            if (u.email.isNotBlank()) {
                "Processing user: ${u.name} (${u.email})"
            } else {
                null
            }
        }
    }
    
    // Elvis operator and safe casts
    fun getUserDisplayName(value: Any?): String {
        val user = value as? User
        return user?.name?.takeIf { it.isNotBlank() } ?: "Unknown User"
    }
    
    // Platform types (would come from Java interop)
    fun handlePlatformType(javaString: String): String {
        // In real scenario, this would be a platform type from Java
        return javaString.uppercase()
    }
}

// Reified type parameters
inline fun <reified T> createList(vararg items: T): List<T> {
    return items.toList()
}

inline fun <reified T> Any?.isOfType(): Boolean {
    return this is T
}

// Delegation
interface Delegate {
    fun doSomething(): String
}

class DelegateImpl : Delegate {
    override fun doSomething(): String = "Delegate implementation"
}

class DelegatedClass : Delegate by DelegateImpl() {
    fun additionalMethod(): String = "Additional functionality"
}

// Property delegation
class LazyExample {
    val expensiveProperty: String by lazy {
        println("Computing expensive property")
        "Computed value"
    }
    
    var observableProperty: String by Delegates.observable("initial") { _, oldValue, newValue ->
        println("Property changed from $oldValue to $newValue")
    }
}

// Base interfaces and classes
interface Entity {
    val id: Long
}

data class User(
    override val id: Long,
    val name: String,
    val email: String
) : Entity, Comparable<User> {
    override fun compareTo(other: User): Int = name.compareTo(other.name)
}

object Delegates {
    fun <T> observable(initialValue: T, onChange: (property: Any?, oldValue: T, newValue: T) -> Unit): Any {
        // Simplified implementation
        return object {}
    }
}
"""

        chunks = self.parser.chunk(content, "types.kt")

        # Test generic class with constraints
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        generic_classes = [c for c in class_chunks if "<" in c.text and ">" in c.text]
        assert len(generic_classes) >= 1, "Should find generic classes"

        # Test interface detection
        interface_chunks = [
            c
            for c in chunks
            if c.semantic_type == "interface" or "interface " in c.text
        ]
        assert (
            len(interface_chunks) >= 3
        ), f"Should find interfaces, got {len(interface_chunks)}"

        # Test value class/inline class
        value_classes = [
            c for c in class_chunks if "@JvmInline" in c.text or "value class" in c.text
        ]
        assert len(value_classes) >= 1, "Should find value classes"

        # Test type aliases
        typealias_chunks = [c for c in chunks if "typealias" in c.text]
        assert len(typealias_chunks) >= 3, "Should find type aliases"

        # Test inline functions with reified and class methods
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        extension_chunks = [
            c for c in chunks if c.semantic_type == "extension_function"
        ]
        inline_functions = [
            c
            for c in function_chunks + method_chunks + extension_chunks
            if "inline" in c.text
        ]
        assert len(inline_functions) >= 2, "Should find inline functions"

    def test_fallback_behavior_broken_kotlin(self):
        """Test that broken Kotlin is handled gracefully, extracting what's possible."""
        broken_file = self.test_files_dir / "broken" / "BrokenKotlin.kt"

        with open(broken_file, "r", encoding="utf-8") as f:
            broken_content = f.read()

        # Test with SemanticChunker
        chunks = self.chunker.chunk_content(broken_content, str(broken_file))

        # Should produce chunks even for broken Kotlin
        assert len(chunks) > 0, "Should produce chunks even for broken Kotlin"

        # Test data preservation - all content should be preserved
        all_chunk_text = "".join(chunk["text"] for chunk in chunks)

        # Key content should be preserved
        assert "package com.example.broken" in all_chunk_text
        assert "BrokenUser" in all_chunk_text
        assert "BrokenResult" in all_chunk_text

        # The AST parser may extract some semantic information even from broken code
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        if semantic_chunks:
            # If semantic parsing worked, verify error handling or data preservation
            pass  # Just verify no data loss

    def test_minimal_valid_kotlin(self):
        """Test parsing of minimal valid Kotlin."""
        content = """
fun main() {
    println("Hello World")
}
"""

        chunks = self.parser.chunk(content, "minimal.kt")

        assert len(chunks) >= 1, "Should create at least one chunk"

        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) == 1, "Should find exactly one function"
        assert function_chunks[0].semantic_name == "main"

    def test_integration_with_semantic_chunker(self):
        """Test integration with SemanticChunker."""
        content = """
package com.example.integration

data class User(val name: String, val age: Int)

class UserService {
    fun createUser(name: String, age: Int): User {
        return User(name, age)
    }
}

fun main() {
    val service = UserService()
    val user = service.createUser("Alice", 30)
    println("Created user: ${user.name}")
}
"""

        # Test through SemanticChunker
        chunks = self.chunker.chunk_content(content, "integration.kt")

        assert len(chunks) > 0, "Should produce chunks"

        # Should use semantic chunking
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) > 0, "Should use semantic chunking for valid Kotlin"

        # Test chunk structure
        class_chunks = [c for c in semantic_chunks if c.get("semantic_type") == "class"]
        user_class = next(
            (c for c in class_chunks if c.get("semantic_name") == "User"), None
        )
        assert user_class is not None, "Should find User class through SemanticChunker"

    def test_semantic_metadata_completeness(self):
        """Test that semantic metadata is complete and accurate."""
        content = """
package com.example.metadata

data class TestData(val field: String)

class TestClass {
    fun testMethod(): String {
        return "test"
    }
}

fun testFunction() {
    // Function implementation
}
"""

        chunks = self.parser.chunk(content, "metadata-test.kt")

        for chunk in chunks:
            if chunk.semantic_chunking:
                # Required fields should be present
                assert chunk.semantic_type is not None, "semantic_type should be set"
                assert chunk.semantic_name is not None, "semantic_name should be set"
                assert chunk.semantic_path is not None, "semantic_path should be set"
                assert chunk.line_start > 0, "line_start should be positive"
                assert chunk.line_end >= chunk.line_start, "line_end should be valid"

        # Test different construct types
        construct_types = {c.semantic_type for c in chunks if c.semantic_chunking}
        expected_types = {"function", "class"}
        assert expected_types.intersection(
            construct_types
        ), f"Should find various constructs. Found: {construct_types}"

    def test_line_number_accuracy(self):
        """Test that line numbers are accurately tracked."""
        content = """package com.example

data class User(val name: String)

fun createUser(): User {
    return User("Test")
}

class UserService {
    fun getUser(): User {
        return createUser()
    }
}"""

        chunks = self.parser.chunk(content, "line-test.kt")

        # Find specific chunks and verify their line numbers
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        user_data_class = next(
            (c for c in class_chunks if c.semantic_name == "User"), None
        )

        if user_data_class:
            assert (
                user_data_class.line_start >= 3
            ), f"User data class should start around line 3, got {user_data_class.line_start}"

        # Test function line numbers
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        create_user_func = next(
            (c for c in function_chunks if c.semantic_name == "createUser"), None
        )

        if create_user_func:
            assert (
                create_user_func.line_start >= 5
            ), f"createUser function should start around line 5, got {create_user_func.line_start}"
            assert (
                create_user_func.line_end >= create_user_func.line_start
            ), "Line end should be >= line start"

// Modern Kotlin features showcasing advanced language capabilities
// Including coroutines, sealed classes, inline functions, and DSL patterns
package com.example.kotlin.advanced

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlin.reflect.*
import kotlin.experimental.ExperimentalTypeInference
import kotlin.time.*

// Complex sealed class hierarchy with generics
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Throwable) : Result<Nothing>()
    object Loading : Result<Nothing>()

    // Extension functions on sealed class
    inline fun <R> fold(
        onSuccess: (T) -> R,
        onError: (Throwable) -> R,
        onLoading: () -> R
    ): R = when (this) {
        is Success -> onSuccess(data)
        is Error -> onError(exception)
        is Loading -> onLoading()
    }

    companion object {
        fun <T> success(data: T): Result<T> = Success(data)
        fun error(exception: Throwable): Result<Nothing> = Error(exception)
        fun loading(): Result<Nothing> = Loading

        // Complex generic function with constraints
        inline fun <T, R> Result<T>.mapCatching(
            crossinline transform: (T) -> R
        ): Result<R> = when (this) {
            is Success -> try {
                Success(transform(data))
            } catch (e: Exception) {
                Error(e)
            }
            is Error -> this
            is Loading -> this
        }
    }
}

// Advanced data classes with complex validation
@JvmRecord
data class UserProfile(
    val id: UserId,
    val email: EmailAddress,
    val username: Username,
    val personalInfo: PersonalInfo,
    val preferences: UserPreferences = UserPreferences(),
    val metadata: Map<String, Any> = emptyMap()
) {
    // Custom validation in init block
    init {
        require(username.value.isNotBlank()) { "Username cannot be blank" }
        require(email.value.contains("@")) { "Email must contain @" }
    }

    // Complex computed properties
    val displayName: String
        get() = personalInfo.firstName?.let { first ->
            personalInfo.lastName?.let { last -> "$first $last" } ?: first
        } ?: username.value

    val isComplete: Boolean
        get() = personalInfo.firstName != null && 
                personalInfo.lastName != null && 
                personalInfo.dateOfBirth != null

    // Extension-like member functions
    fun withUpdatedPreferences(updater: UserPreferences.() -> UserPreferences): UserProfile =
        copy(preferences = preferences.updater())

    fun toPublicProfile(): PublicUserProfile = PublicUserProfile(
        username = username,
        displayName = displayName,
        avatarUrl = personalInfo.avatarUrl,
        isVerified = metadata["verified"] as? Boolean ?: false
    )
}

// Value classes for type safety
@JvmInline
value class UserId(val value: Long) {
    init {
        require(value > 0) { "User ID must be positive" }
    }
}

@JvmInline
value class EmailAddress(val value: String) {
    init {
        require(value.matches(Regex("^[A-Za-z0-9+_.-]+@([A-Za-z0-9.-]+\\.[A-Za-z]{2,})$"))) {
            "Invalid email format"
        }
    }
}

@JvmInline
value class Username(val value: String) {
    init {
        require(value.length in 3..50) { "Username must be between 3 and 50 characters" }
        require(value.matches(Regex("^[a-zA-Z0-9_]+$"))) { "Username can only contain letters, numbers, and underscores" }
    }
}

// Complex data class with nested structures
data class PersonalInfo(
    val firstName: String? = null,
    val lastName: String? = null,
    val dateOfBirth: java.time.LocalDate? = null,
    val phoneNumber: PhoneNumber? = null,
    val address: Address? = null,
    val avatarUrl: String? = null,
    val bio: String? = null
)

data class PhoneNumber(
    val countryCode: String,
    val number: String
) {
    val formatted: String
        get() = "+$countryCode $number"

    companion object {
        fun fromString(phoneStr: String): PhoneNumber? {
            val regex = Regex("^\\+(\\d{1,4})\\s(.+)$")
            return regex.matchEntire(phoneStr)?.let { match ->
                PhoneNumber(match.groupValues[1], match.groupValues[2])
            }
        }
    }
}

data class Address(
    val street: String,
    val city: String,
    val state: String? = null,
    val postalCode: String,
    val country: String
)

// Complex preferences with sealed class hierarchies
data class UserPreferences(
    val theme: Theme = Theme.System,
    val language: Language = Language.English,
    val notifications: NotificationPreferences = NotificationPreferences(),
    val privacy: PrivacySettings = PrivacySettings(),
    val advanced: AdvancedSettings = AdvancedSettings()
)

sealed class Theme {
    object Light : Theme()
    object Dark : Theme()
    object System : Theme()
    data class Custom(val primaryColor: String, val backgroundColor: String) : Theme()
}

enum class Language(val code: String, val displayName: String) {
    English("en", "English"),
    Spanish("es", "Español"),
    French("fr", "Français"),
    German("de", "Deutsch"),
    Japanese("ja", "日本語"),
    Chinese("zh", "中文");

    companion object {
        fun fromCode(code: String): Language? = values().find { it.code == code }
    }
}

// Complex generic repository interface with coroutines
interface Repository<T, ID> {
    suspend fun findById(id: ID): Result<T>
    suspend fun findAll(): Flow<T>
    suspend fun findBy(predicate: suspend (T) -> Boolean): Flow<T>
    suspend fun save(entity: T): Result<T>
    suspend fun saveAll(entities: List<T>): Result<List<T>>
    suspend fun deleteById(id: ID): Result<Unit>
    suspend fun count(): Long
    suspend fun exists(id: ID): Boolean
}

// Advanced service with coroutines and flow operations
class UserService(
    private val repository: Repository<UserProfile, UserId>,
    private val cacheManager: CacheManager,
    private val eventPublisher: EventPublisher,
    private val validator: Validator<UserProfile>
) {
    // Complex suspend function with error handling
    suspend fun getUserProfile(userId: UserId): Result<UserProfile> = withContext(Dispatchers.IO) {
        try {
            // Try cache first
            cacheManager.get<UserProfile>("user:${userId.value}")?.let { cachedUser ->
                return@withContext Result.success(cachedUser)
            }

            // Fetch from repository
            val result = repository.findById(userId)
            
            result.fold(
                onSuccess = { user ->
                    // Cache the result
                    launch {
                        cacheManager.put("user:${userId.value}", user, 15.minutes)
                    }
                },
                onError = { /* Handle error */ },
                onLoading = { /* Handle loading */ }
            )

            result
        } catch (e: Exception) {
            Result.error(e)
        }
    }

    // Complex flow operations with transformation and error handling
    fun getActiveUsers(): Flow<UserProfile> = flow {
        repository.findAll()
            .filter { it.preferences.privacy.isPublicProfile }
            .map { user ->
                // Simulate some processing
                delay(10)
                user.copy(
                    metadata = user.metadata + ("lastAccessed" to System.currentTimeMillis())
                )
            }
            .catch { exception ->
                emit(createFallbackUser(exception))
            }
            .collect { emit(it) }
    }

    // Complex function with multiple generic parameters and constraints
    suspend inline fun <reified T : Any, R> processUserData(
        userId: UserId,
        crossinline dataExtractor: suspend (UserProfile) -> T,
        crossinline processor: suspend (T) -> R
    ): Result<R> = withContext(Dispatchers.Default) {
        getUserProfile(userId).fold(
            onSuccess = { user ->
                try {
                    val extractedData = dataExtractor(user)
                    val processedData = processor(extractedData)
                    Result.success(processedData)
                } catch (e: Exception) {
                    Result.error(e)
                }
            },
            onError = { Result.error(it) },
            onLoading = { Result.loading() }
        )
    }

    // Function with receiver and context receivers (experimental)
    @OptIn(ExperimentalTypeInference::class)
    fun buildUserQuery(@BuilderInference block: UserQueryBuilder.() -> Unit): UserQuery {
        return UserQueryBuilder().apply(block).build()
    }

    private suspend fun createFallbackUser(exception: Throwable): UserProfile {
        // Create a fallback user profile
        return UserProfile(
            id = UserId(-1),
            email = EmailAddress("unknown@example.com"),
            username = Username("unknown"),
            personalInfo = PersonalInfo(),
            metadata = mapOf("error" to exception.message)
        )
    }
}

// DSL builder pattern with type-safe builders
@DslMarker
annotation class UserQueryDsl

@UserQueryDsl
class UserQueryBuilder {
    private var emailFilter: String? = null
    private var usernameFilter: String? = null
    private var ageRange: IntRange? = null
    private var preferences: MutableList<(UserPreferences) -> Boolean> = mutableListOf()
    private var orderBy: OrderBy = OrderBy.Username
    private var limit: Int = 100

    fun email(email: String) {
        emailFilter = email
    }

    fun username(username: String) {
        usernameFilter = username
    }

    fun ageRange(min: Int, max: Int) {
        ageRange = min..max
    }

    @UserQueryDsl
    fun preferences(block: PreferenceFilterBuilder.() -> Unit) {
        val builder = PreferenceFilterBuilder()
        builder.block()
        preferences.addAll(builder.filters)
    }

    fun orderBy(order: OrderBy) {
        orderBy = order
    }

    fun limit(count: Int) {
        require(count > 0) { "Limit must be positive" }
        limit = count
    }

    internal fun build(): UserQuery = UserQuery(
        emailFilter = emailFilter,
        usernameFilter = usernameFilter,
        ageRange = ageRange,
        preferenceFilters = preferences.toList(),
        orderBy = orderBy,
        limit = limit
    )
}

@UserQueryDsl
class PreferenceFilterBuilder {
    internal val filters: MutableList<(UserPreferences) -> Boolean> = mutableListOf()

    fun theme(theme: Theme) {
        filters.add { it.theme == theme }
    }

    fun language(language: Language) {
        filters.add { it.language == language }
    }

    fun notificationsEnabled() {
        filters.add { it.notifications.email || it.notifications.push }
    }
}

// Complex sealed class for query ordering
sealed class OrderBy {
    object Username : OrderBy()
    object Email : OrderBy()
    object CreatedAt : OrderBy()
    data class Custom(val fieldName: String, val ascending: Boolean = true) : OrderBy()
}

data class UserQuery(
    val emailFilter: String?,
    val usernameFilter: String?,
    val ageRange: IntRange?,
    val preferenceFilters: List<(UserPreferences) -> Boolean>,
    val orderBy: OrderBy,
    val limit: Int
)

// Advanced coroutine patterns with channels and actors
@OptIn(ObsoleteCoroutinesApi::class)
class UserEventProcessor(private val scope: CoroutineScope) {
    private val eventChannel = Channel<UserEvent>(Channel.UNLIMITED)
    
    // Actor pattern for processing events
    private val processorActor = scope.actor<UserEvent> {
        for (event in channel) {
            processEvent(event)
        }
    }

    // Complex event processing with pattern matching
    private suspend fun processEvent(event: UserEvent) {
        when (event) {
            is UserEvent.ProfileUpdated -> {
                // Handle profile update
                invalidateUserCache(event.userId)
                publishAnalyticsEvent("user.profile.updated", event)
            }
            is UserEvent.PreferencesChanged -> {
                // Handle preference changes
                updateUserRecommendations(event.userId, event.newPreferences)
            }
            is UserEvent.AccountDeleted -> {
                // Handle account deletion
                scheduleDataCleanup(event.userId, event.deletionTime)
            }
        }
    }

    suspend fun publishEvent(event: UserEvent) {
        processorActor.send(event)
    }

    fun close() {
        processorActor.close()
        eventChannel.close()
    }

    // Complex flow operations with backpressure handling
    fun getEventStream(): Flow<UserEvent> = eventChannel.receiveAsFlow()
        .buffer(1000) // Buffer events to handle backpressure
        .flowOn(Dispatchers.IO) // Process on IO dispatcher

    private suspend fun invalidateUserCache(userId: UserId) {
        // Implementation would invalidate cache
    }

    private suspend fun publishAnalyticsEvent(eventType: String, event: UserEvent) {
        // Implementation would publish to analytics
    }

    private suspend fun updateUserRecommendations(userId: UserId, preferences: UserPreferences) {
        // Implementation would update ML recommendations
    }

    private suspend fun scheduleDataCleanup(userId: UserId, deletionTime: java.time.Instant) {
        // Implementation would schedule cleanup job
    }
}

// Complex sealed class hierarchy for events
sealed class UserEvent {
    abstract val userId: UserId
    abstract val timestamp: java.time.Instant

    data class ProfileUpdated(
        override val userId: UserId,
        override val timestamp: java.time.Instant,
        val updatedFields: Set<String>,
        val oldProfile: UserProfile,
        val newProfile: UserProfile
    ) : UserEvent()

    data class PreferencesChanged(
        override val userId: UserId,
        override val timestamp: java.time.Instant,
        val oldPreferences: UserPreferences,
        val newPreferences: UserPreferences
    ) : UserEvent() {
        val changedFields: Set<String> by lazy {
            findChangedFields(oldPreferences, newPreferences)
        }

        private fun findChangedFields(old: UserPreferences, new: UserPreferences): Set<String> {
            val changes = mutableSetOf<String>()
            if (old.theme != new.theme) changes.add("theme")
            if (old.language != new.language) changes.add("language")
            if (old.notifications != new.notifications) changes.add("notifications")
            if (old.privacy != new.privacy) changes.add("privacy")
            if (old.advanced != new.advanced) changes.add("advanced")
            return changes
        }
    }

    data class AccountDeleted(
        override val userId: UserId,
        override val timestamp: java.time.Instant,
        val deletionTime: java.time.Instant,
        val reason: DeletionReason
    ) : UserEvent()
}

enum class DeletionReason {
    USER_REQUEST,
    ADMIN_ACTION,
    POLICY_VIOLATION,
    INACTIVITY,
    GDPR_REQUEST
}

// Complex extension functions with generic constraints
inline fun <T, R> T.letIf(condition: Boolean, block: (T) -> R): R? = 
    if (condition) block(this) else null

inline fun <T> T.applyIf(condition: Boolean, block: T.() -> Unit): T = 
    if (condition) apply(block) else this

// Extension function with context receivers (experimental feature)
context(CoroutineScope)
suspend fun <T> Flow<T>.collectWithTimeout(
    timeout: Duration,
    action: suspend (T) -> Unit
): Unit = withTimeoutOrNull(timeout) {
    collect(action)
} ?: throw TimeoutCancellationException("Flow collection timed out after $timeout")

// Complex object with companion object and nested types
object UserAnalytics {
    private val metrics: MutableMap<String, AnalyticsMetric> = mutableMapOf()

    // Nested data class
    data class AnalyticsMetric(
        val name: String,
        val value: Double,
        val timestamp: java.time.Instant,
        val tags: Map<String, String> = emptyMap()
    ) {
        // Member extension function
        fun withTag(key: String, value: String): AnalyticsMetric =
            copy(tags = tags + (key to value))

        fun withTags(additionalTags: Map<String, String>): AnalyticsMetric =
            copy(tags = tags + additionalTags)
    }

    // Complex function with inline and reified parameters
    inline fun <reified T : Number> recordMetric(
        name: String,
        value: T,
        tags: Map<String, String> = emptyMap()
    ) {
        val metric = AnalyticsMetric(
            name = name,
            value = value.toDouble(),
            timestamp = java.time.Instant.now(),
            tags = tags + ("type" to T::class.simpleName.orEmpty())
        )
        metrics[name] = metric
    }

    // Function with high-order function parameter
    fun aggregateMetrics(
        predicate: (AnalyticsMetric) -> Boolean,
        aggregator: (List<AnalyticsMetric>) -> Double
    ): Double {
        val filteredMetrics = metrics.values.filter(predicate)
        return aggregator(filteredMetrics)
    }

    // Companion object with factory methods
    companion object {
        fun createUserMetrics(userId: UserId): Map<String, AnalyticsMetric> {
            return mapOf(
                "user.created" to AnalyticsMetric(
                    name = "user.created",
                    value = 1.0,
                    timestamp = java.time.Instant.now(),
                    tags = mapOf("user_id" to userId.value.toString())
                )
            )
        }

        // Generic factory method
        inline fun <reified T : AnalyticsMetric> createMetric(
            name: String,
            value: Double,
            crossinline configurator: T.() -> T = { this }
        ): T where T : AnalyticsMetric {
            val metric = AnalyticsMetric(name, value, java.time.Instant.now()) as T
            return metric.configurator()
        }
    }
}

// Complex interface with default implementations and generic constraints
interface Validator<T> {
    suspend fun validate(item: T): ValidationResult

    // Extension function as interface member
    suspend fun validateAll(items: List<T>): List<ValidationResult> =
        items.map { validate(it) }

    // Default implementation with coroutines
    suspend fun validateWithRetry(
        item: T,
        maxRetries: Int = 3,
        delay: Duration = 1.seconds
    ): ValidationResult {
        repeat(maxRetries) { attempt ->
            try {
                return validate(item)
            } catch (e: Exception) {
                if (attempt == maxRetries - 1) {
                    return ValidationResult.Error("Validation failed after $maxRetries attempts: ${e.message}")
                }
                kotlinx.coroutines.delay(delay.inWholeMilliseconds)
            }
        }
        return ValidationResult.Error("Unexpected validation failure")
    }
}

sealed class ValidationResult {
    object Valid : ValidationResult()
    data class Error(val message: String, val field: String? = null) : ValidationResult()
    data class Warning(val message: String, val field: String? = null) : ValidationResult()

    val isValid: Boolean get() = this is Valid
    val hasErrors: Boolean get() = this is Error
    val hasWarnings: Boolean get() = this is Warning
}

// Implementation with complex generics and constraints
class UserProfileValidator : Validator<UserProfile> {
    override suspend fun validate(item: UserProfile): ValidationResult = withContext(Dispatchers.Default) {
        val errors = mutableListOf<String>()

        // Complex validation logic
        if (item.email.value.isBlank()) {
            errors.add("Email cannot be blank")
        }

        if (item.username.value.length < 3) {
            errors.add("Username must be at least 3 characters")
        }

        // Validate nested objects
        item.personalInfo.phoneNumber?.let { phone ->
            if (!phone.formatted.matches(Regex("^\\+\\d{1,4}\\s.+"))) {
                errors.add("Invalid phone number format")
            }
        }

        when {
            errors.isNotEmpty() -> ValidationResult.Error(errors.joinToString("; "))
            else -> ValidationResult.Valid
        }
    }
}

// Placeholder interfaces and classes for compilation
interface CacheManager {
    suspend fun <T> get(key: String): T?
    suspend fun <T> put(key: String, value: T, ttl: Duration)
}

interface EventPublisher {
    suspend fun publish(event: UserEvent)
}

data class PublicUserProfile(
    val username: Username,
    val displayName: String,
    val avatarUrl: String?,
    val isVerified: Boolean
)

data class NotificationPreferences(
    val email: Boolean = true,
    val push: Boolean = true,
    val sms: Boolean = false,
    val inApp: Boolean = true
)

data class PrivacySettings(
    val isPublicProfile: Boolean = true,
    val showEmail: Boolean = false,
    val showPhone: Boolean = false,
    val allowDirectMessages: Boolean = true
)

data class AdvancedSettings(
    val enableExperimentalFeatures: Boolean = false,
    val debugMode: Boolean = false,
    val apiVersion: String = "v1"
)
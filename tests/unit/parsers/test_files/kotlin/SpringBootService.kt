package com.example.springservice

import org.springframework.boot.SpringApplication
import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.context.annotation.Configuration
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.web.bind.annotation.*
import org.springframework.web.server.ResponseStatusException
import java.time.LocalDateTime
import java.util.*
import javax.persistence.*
import javax.validation.Valid
import javax.validation.constraints.*
import kotlinx.coroutines.*
import org.springframework.scheduling.annotation.Async
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.cache.annotation.Cacheable
import org.springframework.security.access.prepost.PreAuthorize
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Value
import org.slf4j.LoggerFactory
import java.util.concurrent.CompletableFuture

@SpringBootApplication
@EnableJpaRepositories
@EnableScheduling
@EnableCaching
class UserServiceApplication {
    companion object {
        @JvmStatic
        fun main(args: Array<String>) {
            SpringApplication.run(UserServiceApplication::class.java, *args)
        }
    }
}

// Entity with modern Kotlin features
@Entity
@Table(name = "users")
data class User(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @Column(nullable = false, length = 100)
    @get:NotBlank(message = "Name is required")
    @get:Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    val name: String = "",

    @Column(nullable = false, unique = true)
    @get:Email(message = "Email should be valid")
    @get:NotBlank(message = "Email is required")
    val email: String = "",

    @Column(name = "created_at")
    val createdAt: LocalDateTime = LocalDateTime.now(),

    @Column(name = "updated_at")
    var updatedAt: LocalDateTime = LocalDateTime.now(),

    @Enumerated(EnumType.STRING)
    val status: UserStatus = UserStatus.ACTIVE,

    @OneToMany(mappedBy = "user", cascade = [CascadeType.ALL], fetch = FetchType.LAZY)
    val orders: List<Order> = emptyList()
) {
    // Custom methods in entity
    fun getDisplayName(): String = name.takeIf { it.isNotBlank() } ?: "Unknown User"
    
    fun isActive(): Boolean = status == UserStatus.ACTIVE
    
    fun getOrderCount(): Int = orders.size
    
    // Update timestamp before save
    @PrePersist
    @PreUpdate
    fun updateTimestamp() {
        updatedAt = LocalDateTime.now()
    }
}

// Enum for user status
enum class UserStatus(val displayName: String) {
    ACTIVE("Active"),
    INACTIVE("Inactive"),
    SUSPENDED("Suspended"),
    DELETED("Deleted");
    
    fun canPerformActions(): Boolean = this == ACTIVE
}

// Related entity
@Entity
@Table(name = "orders")
data class Order(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id")
    val user: User? = null,

    @Column(nullable = false)
    val amount: Double = 0.0,

    @Column(name = "order_date")
    val orderDate: LocalDateTime = LocalDateTime.now(),

    @Enumerated(EnumType.STRING)
    val status: OrderStatus = OrderStatus.PENDING
)

enum class OrderStatus {
    PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED
}

// Repository interfaces
interface UserRepository : JpaRepository<User, Long> {
    
    @Query("SELECT u FROM User u WHERE u.email = :email")
    fun findByEmail(email: String): User?
    
    @Query("SELECT u FROM User u WHERE u.status = :status")
    fun findByStatus(status: UserStatus): List<User>
    
    @Query("SELECT u FROM User u WHERE u.name LIKE %:name%")
    fun findByNameContaining(name: String): List<User>
    
    @Query(value = "SELECT * FROM users WHERE created_at >= :date", nativeQuery = true)
    fun findUsersCreatedAfter(date: LocalDateTime): List<User>
    
    fun countByStatus(status: UserStatus): Long
}

interface OrderRepository : JpaRepository<Order, Long> {
    
    fun findByUserId(userId: Long): List<Order>
    
    fun findByStatus(status: OrderStatus): List<Order>
    
    @Query("SELECT SUM(o.amount) FROM Order o WHERE o.user.id = :userId")
    fun getTotalAmountByUserId(userId: Long): Double?
}

// DTOs with validation
data class CreateUserRequest(
    @get:NotBlank(message = "Name is required")
    @get:Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    val name: String,

    @get:Email(message = "Email should be valid")
    @get:NotBlank(message = "Email is required")
    val email: String
) {
    fun toUser(): User = User(name = name, email = email)
}

data class UpdateUserRequest(
    @get:Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    val name: String? = null,

    @get:Email(message = "Email should be valid")
    val email: String? = null,

    val status: UserStatus? = null
)

data class UserResponse(
    val id: Long,
    val name: String,
    val email: String,
    val status: UserStatus,
    val createdAt: LocalDateTime,
    val updatedAt: LocalDateTime,
    val orderCount: Int
) {
    companion object {
        fun fromUser(user: User): UserResponse = UserResponse(
            id = user.id,
            name = user.name,
            email = user.email,
            status = user.status,
            createdAt = user.createdAt,
            updatedAt = user.updatedAt,
            orderCount = user.getOrderCount()
        )
    }
}

data class PagedResponse<T>(
    val content: List<T>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
    val totalPages: Int,
    val isFirst: Boolean,
    val isLast: Boolean
)

// Service layer with business logic
@Service
@Transactional
class UserService @Autowired constructor(
    private val userRepository: UserRepository,
    private val orderRepository: OrderRepository
) {
    
    companion object {
        private val logger = LoggerFactory.getLogger(UserService::class.java)
        private const val CACHE_NAME = "users"
    }
    
    @Value("\${app.user.max-inactive-days:30}")
    private val maxInactiveDays: Long = 30
    
    @Cacheable(CACHE_NAME)
    fun findById(id: Long): UserResponse {
        logger.info("Finding user by id: $id")
        
        val user = userRepository.findById(id).orElseThrow {
            ResponseStatusException(HttpStatus.NOT_FOUND, "User not found with id: $id")
        }
        
        return UserResponse.fromUser(user)
    }
    
    fun findByEmail(email: String): UserResponse? {
        logger.info("Finding user by email: $email")
        
        return userRepository.findByEmail(email)?.let { user ->
            UserResponse.fromUser(user)
        }
    }
    
    fun getAllUsers(page: Int = 0, size: Int = 20): PagedResponse<UserResponse> {
        logger.info("Getting all users - page: $page, size: $size")
        
        val pageRequest = PageRequest.of(page, size)
        val userPage = userRepository.findAll(pageRequest)
        
        val userResponses = userPage.content.map { user ->
            UserResponse.fromUser(user)
        }
        
        return PagedResponse(
            content = userResponses,
            page = userPage.number,
            size = userPage.size,
            totalElements = userPage.totalElements,
            totalPages = userPage.totalPages,
            isFirst = userPage.isFirst,
            isLast = userPage.isLast
        )
    }
    
    fun createUser(request: CreateUserRequest): UserResponse {
        logger.info("Creating new user with email: ${request.email}")
        
        // Check if user already exists
        userRepository.findByEmail(request.email)?.let {
            throw ResponseStatusException(HttpStatus.CONFLICT, "User with email ${request.email} already exists")
        }
        
        val user = request.toUser()
        val savedUser = userRepository.save(user)
        
        logger.info("User created successfully with id: ${savedUser.id}")
        return UserResponse.fromUser(savedUser)
    }
    
    fun updateUser(id: Long, request: UpdateUserRequest): UserResponse {
        logger.info("Updating user with id: $id")
        
        val user = userRepository.findById(id).orElseThrow {
            ResponseStatusException(HttpStatus.NOT_FOUND, "User not found with id: $id")
        }
        
        // Update fields if provided
        val updatedUser = user.copy(
            name = request.name ?: user.name,
            email = request.email ?: user.email,
            status = request.status ?: user.status,
            updatedAt = LocalDateTime.now()
        )
        
        // Check email uniqueness if changed
        if (request.email != null && request.email != user.email) {
            userRepository.findByEmail(request.email)?.let { existingUser ->
                if (existingUser.id != id) {
                    throw ResponseStatusException(HttpStatus.CONFLICT, "Email ${request.email} is already in use")
                }
            }
        }
        
        val savedUser = userRepository.save(updatedUser)
        logger.info("User updated successfully with id: $id")
        
        return UserResponse.fromUser(savedUser)
    }
    
    fun deleteUser(id: Long) {
        logger.info("Deleting user with id: $id")
        
        val user = userRepository.findById(id).orElseThrow {
            ResponseStatusException(HttpStatus.NOT_FOUND, "User not found with id: $id")
        }
        
        // Soft delete by changing status
        val deletedUser = user.copy(
            status = UserStatus.DELETED,
            updatedAt = LocalDateTime.now()
        )
        
        userRepository.save(deletedUser)
        logger.info("User marked as deleted with id: $id")
    }
    
    fun getUserStats(userId: Long): UserStatsResponse {
        logger.info("Getting user stats for id: $userId")
        
        val user = userRepository.findById(userId).orElseThrow {
            ResponseStatusException(HttpStatus.NOT_FOUND, "User not found with id: $userId")
        }
        
        val orders = orderRepository.findByUserId(userId)
        val totalAmount = orderRepository.getTotalAmountByUserId(userId) ?: 0.0
        
        return UserStatsResponse(
            userId = userId,
            totalOrders = orders.size,
            totalAmount = totalAmount,
            averageOrderAmount = if (orders.isNotEmpty()) totalAmount / orders.size else 0.0,
            lastOrderDate = orders.maxByOrNull { it.orderDate }?.orderDate
        )
    }
    
    // Async method for heavy operations
    @Async
    fun processUserAnalytics(userId: Long): CompletableFuture<String> {
        logger.info("Processing analytics for user: $userId")
        
        return CompletableFuture.supplyAsync {
            Thread.sleep(5000) // Simulate heavy processing
            "Analytics processed for user $userId"
        }
    }
    
    // Scheduled method
    @Scheduled(cron = "0 0 2 * * ?") // Run daily at 2 AM
    fun cleanupInactiveUsers() {
        logger.info("Starting cleanup of inactive users")
        
        val cutoffDate = LocalDateTime.now().minusDays(maxInactiveDays)
        val inactiveUsers = userRepository.findUsersCreatedAfter(cutoffDate)
        
        logger.info("Found ${inactiveUsers.size} inactive users to process")
        
        inactiveUsers.forEach { user ->
            if (user.status == UserStatus.ACTIVE && user.updatedAt.isBefore(cutoffDate)) {
                val updatedUser = user.copy(
                    status = UserStatus.INACTIVE,
                    updatedAt = LocalDateTime.now()
                )
                userRepository.save(updatedUser)
                logger.debug("Marked user ${user.id} as inactive")
            }
        }
    }
}

// Additional data classes
data class UserStatsResponse(
    val userId: Long,
    val totalOrders: Int,
    val totalAmount: Double,
    val averageOrderAmount: Double,
    val lastOrderDate: LocalDateTime?
)

// REST Controller
@RestController
@RequestMapping("/api/users")
@CrossOrigin(origins = ["http://localhost:3000"])
class UserController @Autowired constructor(
    private val userService: UserService
) {
    
    companion object {
        private val logger = LoggerFactory.getLogger(UserController::class.java)
    }
    
    @GetMapping
    fun getAllUsers(
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int
    ): ResponseEntity<PagedResponse<UserResponse>> {
        logger.info("GET /api/users - page: $page, size: $size")
        
        val users = userService.getAllUsers(page, size)
        return ResponseEntity.ok(users)
    }
    
    @GetMapping("/{id}")
    fun getUserById(@PathVariable id: Long): ResponseEntity<UserResponse> {
        logger.info("GET /api/users/$id")
        
        val user = userService.findById(id)
        return ResponseEntity.ok(user)
    }
    
    @GetMapping("/email/{email}")
    fun getUserByEmail(@PathVariable email: String): ResponseEntity<UserResponse> {
        logger.info("GET /api/users/email/$email")
        
        return userService.findByEmail(email)?.let { user ->
            ResponseEntity.ok(user)
        } ?: ResponseEntity.notFound().build()
    }
    
    @PostMapping
    @PreAuthorize("hasRole('ADMIN') or hasRole('USER_MANAGER')")
    fun createUser(@Valid @RequestBody request: CreateUserRequest): ResponseEntity<UserResponse> {
        logger.info("POST /api/users - Creating user with email: ${request.email}")
        
        val user = userService.createUser(request)
        return ResponseEntity.status(HttpStatus.CREATED).body(user)
    }
    
    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN') or hasRole('USER_MANAGER') or principal.id == #id")
    fun updateUser(
        @PathVariable id: Long,
        @Valid @RequestBody request: UpdateUserRequest
    ): ResponseEntity<UserResponse> {
        logger.info("PUT /api/users/$id")
        
        val user = userService.updateUser(id, request)
        return ResponseEntity.ok(user)
    }
    
    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    fun deleteUser(@PathVariable id: Long): ResponseEntity<Void> {
        logger.info("DELETE /api/users/$id")
        
        userService.deleteUser(id)
        return ResponseEntity.noContent().build()
    }
    
    @GetMapping("/{id}/stats")
    fun getUserStats(@PathVariable id: Long): ResponseEntity<UserStatsResponse> {
        logger.info("GET /api/users/$id/stats")
        
        val stats = userService.getUserStats(id)
        return ResponseEntity.ok(stats)
    }
    
    @PostMapping("/{id}/analytics")
    fun processUserAnalytics(@PathVariable id: Long): ResponseEntity<String> {
        logger.info("POST /api/users/$id/analytics")
        
        userService.processUserAnalytics(id)
        return ResponseEntity.accepted().body("Analytics processing started for user $id")
    }
}

// Configuration class
@Configuration
class UserServiceConfiguration {
    
    @Bean
    fun objectMapper(): ObjectMapper = ObjectMapper().apply {
        registerModule(JavaTimeModule())
        disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    }
    
    @Bean
    fun taskExecutor(): TaskExecutor = ThreadPoolTaskExecutor().apply {
        corePoolSize = 4
        maxPoolSize = 8
        queueCapacity = 100
        setThreadNamePrefix("user-service-")
        initialize()
    }
}

// Exception handling
@ControllerAdvice
class GlobalExceptionHandler {
    
    companion object {
        private val logger = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)
    }
    
    @ExceptionHandler(ResponseStatusException::class)
    fun handleResponseStatusException(ex: ResponseStatusException): ResponseEntity<ErrorResponse> {
        logger.warn("Response status exception: ${ex.message}")
        
        val error = ErrorResponse(
            status = ex.status.value(),
            message = ex.reason ?: "Unknown error",
            timestamp = LocalDateTime.now()
        )
        
        return ResponseEntity.status(ex.status).body(error)
    }
    
    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidationException(ex: MethodArgumentNotValidException): ResponseEntity<ErrorResponse> {
        logger.warn("Validation exception: ${ex.message}")
        
        val errors = ex.bindingResult.fieldErrors.map { error ->
            "${error.field}: ${error.defaultMessage}"
        }
        
        val error = ErrorResponse(
            status = HttpStatus.BAD_REQUEST.value(),
            message = "Validation failed: ${errors.joinToString(", ")}",
            timestamp = LocalDateTime.now()
        )
        
        return ResponseEntity.badRequest().body(error)
    }
}

data class ErrorResponse(
    val status: Int,
    val message: String,
    val timestamp: LocalDateTime
)

// Utility extensions
fun String.toUserStatus(): UserStatus? = try {
    UserStatus.valueOf(this.uppercase())
} catch (e: IllegalArgumentException) {
    null
}

fun LocalDateTime.isOlderThan(days: Long): Boolean = 
    this.isBefore(LocalDateTime.now().minusDays(days))

// Custom annotations
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class Auditable

@Target(AnnotationTarget.CLASS)
@Retention(AnnotationRetention.RUNTIME)  
annotation class ApiVersion(val value: String)
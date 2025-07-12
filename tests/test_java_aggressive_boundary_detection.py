"""
Aggressive Java boundary detection tests that push the limits of line tracking.

These tests specifically target edge cases that could cause context pollution,
content bleeding between chunks, and line number inaccuracies in Java code.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker


class TestJavaAggressiveBoundaryDetection:
    """Test Java code that specifically challenges boundary detection."""

    @pytest.fixture
    def text_chunker(self):
        """Create text chunker with small chunk size to force aggressive splitting."""
        config = IndexingConfig()
        config.chunk_size = 800  # Small to force splits in tricky places
        config.chunk_overlap = 50
        return TextChunker(config)

    @pytest.mark.skip(
        reason="Java multi-line construct boundary detection needs enhancement"
    )
    def test_deeply_nested_exception_chaining(self, text_chunker):
        """Test complex exception chaining that could cause bleeding."""
        code = dedent(
            """
            public class ComplexExceptionHandler {
                public void processRequest(UserRequest request) throws ProcessingException {
                    try {
                        validateRequest(request);
                        processUserData(request.getUserData());
                        performBusinessLogic(request);
                    } catch (ValidationException e) {
                        throw new ProcessingException(
                            "Request validation failed for user: " + request.getUserId() + ". " +
                            "The following validation errors occurred: " +
                            "- Email format is invalid: " + e.getFieldValue() + " " +
                            "- Password strength requirements not met " +
                            "- User age must be between 18 and 120 years " +
                            "- Phone number format is incorrect " +
                            "Please correct these issues and try again.",
                            "VALIDATION_FAILED",
                            e
                        );
                    } catch (DataAccessException e) {
                        throw new ProcessingException(
                            "Database operation failed while processing request " + request.getRequestId() + ". " +
                            "Error details: " + e.getMessage() + ". " +
                            "This could be due to: " +
                            "- Network connectivity issues " +
                            "- Database server unavailable " +
                            "- Insufficient database permissions " +
                            "- Query timeout occurred " +
                            "Please contact system administrator if problem persists.",
                            "DATABASE_ERROR",
                            e
                        );
                    } catch (BusinessLogicException e) {
                        if (e.getErrorCode().equals("INSUFFICIENT_FUNDS")) {
                            throw new ProcessingException(
                                "Transaction cannot be completed due to insufficient funds. " +
                                "Account balance: $" + e.getCurrentBalance() + ". " +
                                "Required amount: $" + e.getRequiredAmount() + ". " +
                                "Additional fees: $" + e.getAdditionalFees() + ". " +
                                "Please ensure sufficient funds are available and try again. " +
                                "You can add funds through: " +
                                "- Online banking transfer " +
                                "- Credit card deposit " +
                                "- Bank branch visit " +
                                "- Mobile app quick transfer",
                                "INSUFFICIENT_FUNDS",
                                e
                            );
                        } else {
                            throw new ProcessingException(
                                "Business rule violation occurred: " + e.getRuleName() + ". " +
                                "Rule description: " + e.getRuleDescription() + ". " +
                                "Current value: " + e.getCurrentValue() + ". " +
                                "Expected value: " + e.getExpectedValue() + ". " +
                                "Violation severity: " + e.getSeverity() + ". " +
                                "This indicates a serious business logic error that requires attention.",
                                "BUSINESS_RULE_VIOLATION",
                                e
                            );
                        }
                    }
                }
                
                private void cleanup() {
                    // Cleanup resources
                }
            }
        """
        ).strip()

        chunks = text_chunker.chunk_text(code)
        original_lines = code.splitlines()

        # Verify no bleeding between exception handling blocks
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            # If chunk contains "INSUFFICIENT_FUNDS" it should NOT contain "BUSINESS_RULE_VIOLATION"
            if (
                "INSUFFICIENT_FUNDS" in chunk_text
                and "BUSINESS_RULE_VIOLATION" in chunk_text
            ):
                # Check if this is actually correct based on line ranges
                expected_content = self._extract_expected_content(
                    original_lines, chunk["line_start"], chunk["line_end"]
                )
                if not (
                    "INSUFFICIENT_FUNDS" in expected_content
                    and "BUSINESS_RULE_VIOLATION" in expected_content
                ):
                    pytest.fail(
                        f"Chunk {i+1} contains bleeding between different exception types! "
                        f"Lines {chunk['line_start']}-{chunk['line_end']} should not contain both."
                    )

            # If chunk contains part of an error message, it should contain the complete message
            if (
                "Transaction cannot be completed due to insufficient funds."
                in chunk_text
            ):
                assert (
                    "- Mobile app quick transfer" in chunk_text
                ), f"Chunk {i+1} has incomplete INSUFFICIENT_FUNDS error message"

            if "Business rule violation occurred:" in chunk_text:
                assert (
                    "This indicates a serious business logic error" in chunk_text
                ), f"Chunk {i+1} has incomplete BUSINESS_RULE_VIOLATION error message"

    @pytest.mark.skip(
        reason="Java multi-line construct boundary detection needs enhancement"
    )
    def test_annotation_heavy_class_with_complex_generics(self, text_chunker):
        """Test class with heavy annotations and generics that could cause confusion."""
        code = dedent(
            """
            @RestController
            @RequestMapping("/api/v1/users")
            @Validated
            @Slf4j
            @CrossOrigin(origins = {
                "http://localhost:3000",
                "https://app.example.com",
                "https://staging.example.com"
            })
            public class UserController<T extends BaseEntity & Serializable, 
                                       R extends BaseResponse<T>,
                                       S extends BaseService<T, R>> {
                
                @Autowired
                @Qualifier("userServiceImpl")
                private final S userService;
                
                @Value("${app.security.jwt.secret:default-secret-key-that-should-be-changed}")
                private String jwtSecret;
                
                @PostMapping(
                    value = "/create",
                    consumes = MediaType.APPLICATION_JSON_VALUE,
                    produces = MediaType.APPLICATION_JSON_VALUE
                )
                @PreAuthorize("hasRole('ADMIN') or hasRole('USER_MANAGER')")
                @Operation(
                    summary = "Create a new user",
                    description = "Creates a new user in the system with full validation. " +
                                 "Requires appropriate permissions and valid user data. " +
                                 "This endpoint performs comprehensive validation including: " +
                                 "- Email uniqueness check " +
                                 "- Password strength validation " +
                                 "- Username availability verification " +
                                 "- Role assignment validation"
                )
                @ApiResponses(value = {
                    @ApiResponse(
                        responseCode = "201",
                        description = "User created successfully",
                        content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(implementation = UserResponse.class)
                        )
                    ),
                    @ApiResponse(
                        responseCode = "400",
                        description = "Invalid user data provided. Check validation errors.",
                        content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(implementation = ErrorResponse.class)
                        )
                    ),
                    @ApiResponse(
                        responseCode = "409",
                        description = "User already exists with provided email or username",
                        content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(implementation = ConflictErrorResponse.class)
                        )
                    )
                })
                public ResponseEntity<R> createUser(
                    @Valid @RequestBody CreateUserRequest request,
                    @RequestHeader(value = "X-Trace-Id", required = false) String traceId,
                    @RequestParam(value = "sendWelcomeEmail", defaultValue = "true") boolean sendEmail
                ) throws ValidationException, UserAlreadyExistsException {
                    
                    if (log.isDebugEnabled()) {
                        log.debug(
                            "Creating user with email: {} and username: {}. " +
                            "Trace ID: {}. " +
                            "Send welcome email: {}. " +
                            "Request originated from: {}",
                            request.getEmail(),
                            request.getUsername(), 
                            traceId,
                            sendEmail,
                            request.getOriginatingSystem()
                        );
                    }
                    
                    return userService.createUser(request, traceId, sendEmail);
                }
            }
        """
        ).strip()

        chunks = text_chunker.chunk_text(code)
        original_lines = code.splitlines()

        # Check for annotation bleeding
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            # If chunk contains part of @ApiResponses, it should contain the complete annotation
            if "@ApiResponses(value = {" in chunk_text:
                if "})" not in chunk_text:
                    # Check if this is expected based on line numbers
                    expected_content = self._extract_expected_content(
                        original_lines, chunk["line_start"], chunk["line_end"]
                    )
                    if (
                        "@ApiResponses(value = {" in expected_content
                        and "})" not in expected_content
                    ):
                        # This is actually expected - the annotation spans multiple chunks
                        continue
                    else:
                        pytest.fail(
                            f"Chunk {i+1} contains incomplete @ApiResponses annotation"
                        )

            # Check for method signature bleeding
            if "public ResponseEntity<R> createUser(" in chunk_text:
                # Should contain the complete method signature
                assert (
                    ") throws ValidationException, UserAlreadyExistsException {"
                    in chunk_text
                ), f"Chunk {i+1} has incomplete method signature"

    @pytest.mark.skip(
        reason="Java multi-line construct boundary detection needs enhancement"
    )
    def test_complex_lambda_and_stream_operations(self, text_chunker):
        """Test complex lambda expressions and stream operations."""
        code = dedent(
            """
            public class DataProcessor {
                public List<ProcessedResult> processUserData(List<User> users) {
                    return users.stream()
                        .filter(user -> {
                            boolean isActive = user.isActive();
                            boolean hasValidEmail = user.getEmail() != null && 
                                                   user.getEmail().matches("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");
                            boolean hasRequiredFields = user.getFirstName() != null && 
                                                       user.getLastName() != null &&
                                                       user.getDateOfBirth() != null;
                            if (!isActive) {
                                log.warn(
                                    "Filtering out inactive user: {} (ID: {}). " +
                                    "User status: {}. " +
                                    "Last login: {}. " +
                                    "Account created: {}",
                                    user.getFullName(),
                                    user.getId(),
                                    user.getStatus(),
                                    user.getLastLoginDate(),
                                    user.getCreatedDate()
                                );
                            }
                            return isActive && hasValidEmail && hasRequiredFields;
                        })
                        .map(user -> {
                            try {
                                ProcessedResult result = new ProcessedResult();
                                result.setUserId(user.getId());
                                result.setFullName(user.getFirstName() + " " + user.getLastName());
                                result.setProcessedDate(LocalDateTime.now());
                                result.setEmail(user.getEmail().toLowerCase().trim());
                                
                                // Calculate user score based on multiple factors
                                double score = calculateUserScore(
                                    user.getLoginFrequency(),
                                    user.getAccountAge(),
                                    user.getTransactionHistory(),
                                    user.getVerificationStatus()
                                );
                                result.setScore(score);
                                
                                // Add additional metadata
                                Map<String, Object> metadata = new HashMap<>();
                                metadata.put("processingTimestamp", System.currentTimeMillis());
                                metadata.put("processingVersion", "2.1.4");
                                metadata.put("dataSource", user.getDataSource());
                                metadata.put("qualityScore", user.getDataQualityScore());
                                result.setMetadata(metadata);
                                
                                if (log.isTraceEnabled()) {
                                    log.trace(
                                        "Successfully processed user: {} (ID: {}). " +
                                        "Score: {}. " +
                                        "Processing time: {}ms. " +
                                        "Data quality: {}",
                                        user.getFullName(),
                                        user.getId(),
                                        score,
                                        System.currentTimeMillis() - startTime,
                                        user.getDataQualityScore()
                                    );
                                }
                                
                                return result;
                            } catch (Exception e) {
                                log.error(
                                    "Failed to process user: {} (ID: {}). " +
                                    "Error type: {}. " +
                                    "Error message: {}. " +
                                    "Stack trace will be logged at DEBUG level. " +
                                    "User data: firstName={}, lastName={}, email={}, status={}",
                                    user.getFullName(),
                                    user.getId(),
                                    e.getClass().getSimpleName(),
                                    e.getMessage(),
                                    user.getFirstName(),
                                    user.getLastName(),
                                    user.getEmail(),
                                    user.getStatus(),
                                    e
                                );
                                return null;
                            }
                        })
                        .filter(Objects::nonNull)
                        .sorted((a, b) -> Double.compare(b.getScore(), a.getScore()))
                        .collect(Collectors.toList());
                }
            }
        """
        ).strip()

        chunks = text_chunker.chunk_text(code)

        # Check that lambda expressions are not split inappropriately
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            # If chunk contains the start of a lambda, it should contain its complete body
            if ".filter(user -> {" in chunk_text:
                # If we see the opening of the lambda, we should see its closing
                lambda_start = chunk_text.find(".filter(user -> {")
                if lambda_start != -1:
                    # Check if we have the complete lambda by looking for the closing pattern
                    if (
                        "return isActive && hasValidEmail && hasRequiredFields;"
                        in chunk_text
                    ):
                        # This chunk should contain the complete filter lambda
                        assert (
                            "})" in chunk_text
                        ), f"Chunk {i+1} contains incomplete filter lambda expression"

            # Check logging statements are complete
            if (
                "log.warn(" in chunk_text
                and "Filtering out inactive user:" in chunk_text
            ):
                assert (
                    "user.getCreatedDate()" in chunk_text
                ), f"Chunk {i+1} has incomplete log.warn statement"

            if "log.error(" in chunk_text and "Failed to process user:" in chunk_text:
                assert (
                    "user.getStatus()," in chunk_text
                ), f"Chunk {i+1} has incomplete log.error statement"

    def _extract_expected_content(self, original_lines, start_line, end_line):
        """Extract expected content based on line numbers."""
        start_idx = start_line - 1
        end_idx = end_line - 1

        if start_idx < 0 or end_idx >= len(original_lines):
            return ""

        return "\\n".join(original_lines[start_idx : end_idx + 1])

    @pytest.mark.skip(
        reason="Java multi-line construct boundary detection needs enhancement"
    )
    def test_interface_with_default_methods_and_complex_javadoc(self, text_chunker):
        """Test interface with default methods that could cause boundary issues."""
        code = dedent(
            """
            /**
             * Comprehensive user service interface with advanced features.
             * 
             * This interface defines the contract for user management operations
             * including CRUD operations, authentication, authorization, and
             * advanced user analytics.
             * 
             * @param <T> the user entity type extending BaseUser
             * @param <R> the response type for user operations
             * @since 2.0.0
             * @author Development Team
             * @see BaseUser
             * @see UserResponse
             */
            @FunctionalInterface
            public interface UserService<T extends BaseUser & Auditable, R extends BaseResponse<T>> {
                
                /**
                 * Creates a new user in the system with comprehensive validation.
                 * 
                 * This method performs the following operations:
                 * 1. Validates user input data according to business rules
                 * 2. Checks for duplicate emails and usernames
                 * 3. Encrypts sensitive information
                 * 4. Persists user data to the database
                 * 5. Sends welcome notification if configured
                 * 6. Logs the creation event for audit purposes
                 * 
                 * @param userData the user data transfer object containing all user information
                 * @param context the execution context with security and session information
                 * @return the created user response with generated ID and metadata
                 * @throws ValidationException if user data fails validation rules
                 * @throws DuplicateUserException if user already exists with same email/username
                 * @throws SecurityException if caller lacks required permissions
                 * @throws SystemException if system error occurs during creation
                 */
                R createUser(T userData, ExecutionContext context) 
                    throws ValidationException, DuplicateUserException, SecurityException, SystemException;
                
                /**
                 * Retrieves user by unique identifier with optional data projection.
                 * 
                 * @param userId the unique user identifier (must be positive)
                 * @param includeDetails whether to include detailed user information
                 * @param projection the fields to include in response (null for all fields)
                 * @return user response if found, empty optional otherwise
                 * @throws InvalidParameterException if userId is invalid
                 * @throws SecurityException if caller lacks read permissions for user
                 */
                default Optional<R> getUserById(Long userId, boolean includeDetails, Set<String> projection) 
                    throws InvalidParameterException, SecurityException {
                    
                    if (userId == null || userId <= 0) {
                        throw new InvalidParameterException(
                            "User ID must be a positive number. " +
                            "Provided value: " + userId + ". " +
                            "Valid range: 1 to " + Long.MAX_VALUE + ". " +
                            "This error typically indicates: " +
                            "- Invalid input validation " +
                            "- Incorrect parameter mapping " +
                            "- Database constraint violation " +
                            "Please verify the user ID and try again."
                        );
                    }
                    
                    try {
                        T user = findUserInDatabase(userId);
                        if (user == null) {
                            if (log.isDebugEnabled()) {
                                log.debug(
                                    "User not found with ID: {}. " +
                                    "Search included details: {}. " +
                                    "Projection fields: {}. " +
                                    "This might be due to: " +
                                    "- User was deleted " +
                                    "- User is in inactive state " +
                                    "- Permission restrictions apply",
                                    userId,
                                    includeDetails,
                                    projection != null ? String.join(", ", projection) : "ALL"
                                );
                            }
                            return Optional.empty();
                        }
                        
                        R response = convertToResponse(user, includeDetails, projection);
                        
                        if (log.isTraceEnabled()) {
                            log.trace(
                                "Successfully retrieved user: {} (ID: {}). " +
                                "Response includes details: {}. " +
                                "Projected fields: {}. " +
                                "Response size: {} bytes",
                                user.getDisplayName(),
                                userId,
                                includeDetails,
                                projection != null ? projection.size() : "ALL",
                                calculateResponseSize(response)
                            );
                        }
                        
                        return Optional.of(response);
                        
                    } catch (DatabaseException e) {
                        log.error(
                            "Database error occurred while retrieving user: {}. " +
                            "Error code: {}. " +
                            "Error message: {}. " +
                            "Query execution time: {}ms. " +
                            "Retry attempt will be made if configured.",
                            userId,
                            e.getErrorCode(),
                            e.getMessage(),
                            e.getExecutionTime()
                        );
                        throw new SystemException("Failed to retrieve user due to database error", e);
                    }
                }
                
                /**
                 * Validates user permissions for specific operations.
                 */
                default boolean hasPermission(Long userId, String operation, String resource) {
                    // Implementation would check user permissions
                    return getPermissionService().checkPermission(userId, operation, resource);
                }
            }
        """
        ).strip()

        chunks = text_chunker.chunk_text(code)

        # Verify that Javadoc comments are not split inappropriately
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            # If chunk contains the start of a method Javadoc, it should be complete
            if "/**" in chunk_text and "Creates a new user in the system" in chunk_text:
                assert (
                    "*/" in chunk_text
                ), f"Chunk {i+1} contains incomplete Javadoc for createUser method"

            # Check that method signatures with throws clauses are complete
            if "R createUser(T userData, ExecutionContext context)" in chunk_text:
                assert (
                    "throws ValidationException, DuplicateUserException, SecurityException, SystemException;"
                    in chunk_text
                ), f"Chunk {i+1} has incomplete createUser method signature"

            # Check that default method implementations are complete
            if "default Optional<R> getUserById(" in chunk_text:
                if "InvalidParameterException" in chunk_text:
                    # This chunk should contain the complete error message
                    assert (
                        "Please verify the user ID and try again." in chunk_text
                    ), f"Chunk {i+1} has incomplete InvalidParameterException message"

            # Check logging statements are complete
            if "log.debug(" in chunk_text and "User not found with ID:" in chunk_text:
                assert (
                    "- Permission restrictions apply" in chunk_text
                ), f"Chunk {i+1} has incomplete log.debug statement"

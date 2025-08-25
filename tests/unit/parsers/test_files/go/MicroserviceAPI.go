package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis/v8"
	"github.com/golang-jwt/jwt/v4"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// Configuration structures
type Config struct {
	Server   ServerConfig   `json:"server"`
	Database DatabaseConfig `json:"database"`
	Redis    RedisConfig    `json:"redis"`
	JWT      JWTConfig      `json:"jwt"`
	Metrics  MetricsConfig  `json:"metrics"`
}

type ServerConfig struct {
	Port         string        `json:"port"`
	ReadTimeout  time.Duration `json:"read_timeout"`
	WriteTimeout time.Duration `json:"write_timeout"`
	IdleTimeout  time.Duration `json:"idle_timeout"`
}

type DatabaseConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	User     string `json:"user"`
	Password string `json:"password"`
	DBName   string `json:"db_name"`
	SSLMode  string `json:"ssl_mode"`
}

type RedisConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Password string `json:"password"`
	DB       int    `json:"db"`
}

type JWTConfig struct {
	SecretKey      string        `json:"secret_key"`
	ExpirationTime time.Duration `json:"expiration_time"`
	Issuer         string        `json:"issuer"`
}

type MetricsConfig struct {
	Enabled bool   `json:"enabled"`
	Path    string `json:"path"`
}

// Domain models
type User struct {
	ID        uint      `json:"id" gorm:"primaryKey"`
	Username  string    `json:"username" gorm:"uniqueIndex;not null"`
	Email     string    `json:"email" gorm:"uniqueIndex;not null"`
	Password  string    `json:"-" gorm:"not null"` // Hidden in JSON
	FirstName string    `json:"first_name"`
	LastName  string    `json:"last_name"`
	Role      UserRole  `json:"role" gorm:"default:user"`
	Status    UserStatus `json:"status" gorm:"default:active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
	
	// Associations
	Orders   []Order   `json:"orders,omitempty" gorm:"foreignKey:UserID"`
	Profile  *Profile  `json:"profile,omitempty" gorm:"foreignKey:UserID"`
	Sessions []Session `json:"-" gorm:"foreignKey:UserID"`
}

type UserRole string

const (
	RoleUser  UserRole = "user"
	RoleAdmin UserRole = "admin"
	RoleMod   UserRole = "moderator"
)

func (r UserRole) IsValid() bool {
	switch r {
	case RoleUser, RoleAdmin, RoleMod:
		return true
	default:
		return false
	}
}

func (r UserRole) HasPermission(action string) bool {
	permissions := map[UserRole][]string{
		RoleUser:  {"read", "create"},
		RoleMod:   {"read", "create", "update"},
		RoleAdmin: {"read", "create", "update", "delete"},
	}
	
	allowed, exists := permissions[r]
	if !exists {
		return false
	}
	
	for _, perm := range allowed {
		if perm == action {
			return true
		}
	}
	return false
}

type UserStatus string

const (
	StatusActive    UserStatus = "active"
	StatusInactive  UserStatus = "inactive"
	StatusSuspended UserStatus = "suspended"
	StatusDeleted   UserStatus = "deleted"
)

func (s UserStatus) IsActive() bool {
	return s == StatusActive
}

type Profile struct {
	ID          uint      `json:"id" gorm:"primaryKey"`
	UserID      uint      `json:"user_id" gorm:"not null"`
	Avatar      string    `json:"avatar"`
	Bio         string    `json:"bio"`
	Location    string    `json:"location"`
	Website     string    `json:"website"`
	DateOfBirth time.Time `json:"date_of_birth"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Order struct {
	ID          uint        `json:"id" gorm:"primaryKey"`
	UserID      uint        `json:"user_id" gorm:"not null"`
	Total       float64     `json:"total" gorm:"type:decimal(10,2)"`
	Currency    string      `json:"currency" gorm:"default:USD"`
	Status      OrderStatus `json:"status" gorm:"default:pending"`
	Items       []OrderItem `json:"items" gorm:"foreignKey:OrderID"`
	CreatedAt   time.Time   `json:"created_at"`
	UpdatedAt   time.Time   `json:"updated_at"`
	CompletedAt *time.Time  `json:"completed_at,omitempty"`
}

type OrderStatus string

const (
	OrderPending   OrderStatus = "pending"
	OrderConfirmed OrderStatus = "confirmed"
	OrderShipped   OrderStatus = "shipped"
	OrderDelivered OrderStatus = "delivered"
	OrderCancelled OrderStatus = "cancelled"
)

func (s OrderStatus) IsTerminal() bool {
	return s == OrderDelivered || s == OrderCancelled
}

type OrderItem struct {
	ID        uint    `json:"id" gorm:"primaryKey"`
	OrderID   uint    `json:"order_id" gorm:"not null"`
	ProductID uint    `json:"product_id" gorm:"not null"`
	Quantity  int     `json:"quantity" gorm:"default:1"`
	Price     float64 `json:"price" gorm:"type:decimal(10,2)"`
	CreatedAt time.Time `json:"created_at"`
}

type Session struct {
	ID        string    `json:"id" gorm:"primaryKey"`
	UserID    uint      `json:"user_id" gorm:"not null"`
	Token     string    `json:"-" gorm:"uniqueIndex"`
	ExpiresAt time.Time `json:"expires_at"`
	CreatedAt time.Time `json:"created_at"`
	UserAgent string    `json:"user_agent"`
	IPAddress string    `json:"ip_address"`
}

// DTOs for API requests/responses
type CreateUserRequest struct {
	Username  string `json:"username" binding:"required,min=3,max=20"`
	Email     string `json:"email" binding:"required,email"`
	Password  string `json:"password" binding:"required,min=8"`
	FirstName string `json:"first_name" binding:"required"`
	LastName  string `json:"last_name" binding:"required"`
}

type UpdateUserRequest struct {
	Username  *string    `json:"username,omitempty" binding:"omitempty,min=3,max=20"`
	Email     *string    `json:"email,omitempty" binding:"omitempty,email"`
	FirstName *string    `json:"first_name,omitempty"`
	LastName  *string    `json:"last_name,omitempty"`
	Role      *UserRole  `json:"role,omitempty"`
	Status    *UserStatus `json:"status,omitempty"`
}

type LoginRequest struct {
	Username string `json:"username" binding:"required"`
	Password string `json:"password" binding:"required"`
}

type LoginResponse struct {
	Token     string    `json:"token"`
	ExpiresAt time.Time `json:"expires_at"`
	User      User      `json:"user"`
}

type CreateOrderRequest struct {
	Items []CreateOrderItemRequest `json:"items" binding:"required,min=1"`
}

type CreateOrderItemRequest struct {
	ProductID uint `json:"product_id" binding:"required"`
	Quantity  int  `json:"quantity" binding:"required,min=1"`
}

type PaginatedResponse[T any] struct {
	Data       []T   `json:"data"`
	Page       int   `json:"page"`
	PerPage    int   `json:"per_page"`
	Total      int64 `json:"total"`
	TotalPages int   `json:"total_pages"`
}

type ErrorResponse struct {
	Error     string                 `json:"error"`
	Message   string                 `json:"message"`
	Details   map[string]interface{} `json:"details,omitempty"`
	Timestamp time.Time              `json:"timestamp"`
}

// JWT Claims
type JWTClaims struct {
	UserID   uint     `json:"user_id"`
	Username string   `json:"username"`
	Role     UserRole `json:"role"`
	jwt.RegisteredClaims
}

// Repository interfaces
type UserRepository interface {
	Create(ctx context.Context, user *User) error
	GetByID(ctx context.Context, id uint) (*User, error)
	GetByUsername(ctx context.Context, username string) (*User, error)
	GetByEmail(ctx context.Context, email string) (*User, error)
	Update(ctx context.Context, user *User) error
	Delete(ctx context.Context, id uint) error
	List(ctx context.Context, limit, offset int) ([]User, int64, error)
	GetUserWithProfile(ctx context.Context, id uint) (*User, error)
}

type OrderRepository interface {
	Create(ctx context.Context, order *Order) error
	GetByID(ctx context.Context, id uint) (*Order, error)
	GetByUserID(ctx context.Context, userID uint, limit, offset int) ([]Order, int64, error)
	Update(ctx context.Context, order *Order) error
	GetUserOrderStats(ctx context.Context, userID uint) (*OrderStats, error)
}

type SessionRepository interface {
	Create(ctx context.Context, session *Session) error
	GetByToken(ctx context.Context, token string) (*Session, error)
	DeleteByUserID(ctx context.Context, userID uint) error
	DeleteExpired(ctx context.Context) error
}

// Repository implementations
type userRepository struct {
	db *gorm.DB
}

func NewUserRepository(db *gorm.DB) UserRepository {
	return &userRepository{db: db}
}

func (r *userRepository) Create(ctx context.Context, user *User) error {
	return r.db.WithContext(ctx).Create(user).Error
}

func (r *userRepository) GetByID(ctx context.Context, id uint) (*User, error) {
	var user User
	err := r.db.WithContext(ctx).First(&user, id).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *userRepository) GetByUsername(ctx context.Context, username string) (*User, error) {
	var user User
	err := r.db.WithContext(ctx).Where("username = ?", username).First(&user).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *userRepository) GetByEmail(ctx context.Context, email string) (*User, error) {
	var user User
	err := r.db.WithContext(ctx).Where("email = ?", email).First(&user).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *userRepository) Update(ctx context.Context, user *User) error {
	return r.db.WithContext(ctx).Save(user).Error
}

func (r *userRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&User{}, id).Error
}

func (r *userRepository) List(ctx context.Context, limit, offset int) ([]User, int64, error) {
	var users []User
	var total int64
	
	// Count total records
	if err := r.db.WithContext(ctx).Model(&User{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	
	// Get paginated results
	err := r.db.WithContext(ctx).
		Limit(limit).
		Offset(offset).
		Order("created_at DESC").
		Find(&users).Error
	
	return users, total, err
}

func (r *userRepository) GetUserWithProfile(ctx context.Context, id uint) (*User, error) {
	var user User
	err := r.db.WithContext(ctx).
		Preload("Profile").
		First(&user, id).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// Service layer
type UserService struct {
	repo         UserRepository
	orderRepo    OrderRepository
	sessionRepo  SessionRepository
	redis        *redis.Client
	jwtSecret    []byte
	logger       *zap.Logger
	metrics      *Metrics
}

type OrderStats struct {
	TotalOrders    int     `json:"total_orders"`
	TotalAmount    float64 `json:"total_amount"`
	AverageAmount  float64 `json:"average_amount"`
	LastOrderDate  *time.Time `json:"last_order_date"`
}

func NewUserService(
	repo UserRepository,
	orderRepo OrderRepository, 
	sessionRepo SessionRepository,
	redis *redis.Client,
	jwtSecret []byte,
	logger *zap.Logger,
	metrics *Metrics,
) *UserService {
	return &UserService{
		repo:        repo,
		orderRepo:   orderRepo,
		sessionRepo: sessionRepo,
		redis:       redis,
		jwtSecret:   jwtSecret,
		logger:      logger,
		metrics:     metrics,
	}
}

func (s *UserService) CreateUser(ctx context.Context, req CreateUserRequest) (*User, error) {
	s.logger.Info("Creating new user", zap.String("username", req.Username))
	
	// Check if username exists
	if existingUser, _ := s.repo.GetByUsername(ctx, req.Username); existingUser != nil {
		return nil, fmt.Errorf("username already exists")
	}
	
	// Check if email exists
	if existingUser, _ := s.repo.GetByEmail(ctx, req.Email); existingUser != nil {
		return nil, fmt.Errorf("email already exists")
	}
	
	// Hash password
	hashedPassword, err := hashPassword(req.Password)
	if err != nil {
		s.logger.Error("Failed to hash password", zap.Error(err))
		return nil, fmt.Errorf("failed to process password")
	}
	
	user := &User{
		Username:  req.Username,
		Email:     req.Email,
		Password:  hashedPassword,
		FirstName: req.FirstName,
		LastName:  req.LastName,
		Role:      RoleUser,
		Status:    StatusActive,
	}
	
	if err := s.repo.Create(ctx, user); err != nil {
		s.logger.Error("Failed to create user", zap.Error(err))
		return nil, fmt.Errorf("failed to create user: %w", err)
	}
	
	s.metrics.UsersCreated.Inc()
	s.logger.Info("User created successfully", zap.Uint("user_id", user.ID))
	
	return user, nil
}

func (s *UserService) GetUser(ctx context.Context, id uint) (*User, error) {
	// Try cache first
	cacheKey := fmt.Sprintf("user:%d", id)
	cached := s.redis.Get(ctx, cacheKey)
	if cached.Err() == nil {
		var user User
		if err := json.Unmarshal([]byte(cached.Val()), &user); err == nil {
			s.metrics.CacheHits.Inc()
			return &user, nil
		}
	}
	
	s.metrics.CacheMisses.Inc()
	user, err := s.repo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	
	// Cache the result
	if userJSON, err := json.Marshal(user); err == nil {
		s.redis.Set(ctx, cacheKey, userJSON, 10*time.Minute)
	}
	
	return user, nil
}

func (s *UserService) UpdateUser(ctx context.Context, id uint, req UpdateUserRequest) (*User, error) {
	user, err := s.repo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	
	// Update fields
	if req.Username != nil {
		user.Username = *req.Username
	}
	if req.Email != nil {
		user.Email = *req.Email
	}
	if req.FirstName != nil {
		user.FirstName = *req.FirstName
	}
	if req.LastName != nil {
		user.LastName = *req.LastName
	}
	if req.Role != nil && req.Role.IsValid() {
		user.Role = *req.Role
	}
	if req.Status != nil {
		user.Status = *req.Status
	}
	
	if err := s.repo.Update(ctx, user); err != nil {
		return nil, err
	}
	
	// Invalidate cache
	cacheKey := fmt.Sprintf("user:%d", id)
	s.redis.Del(ctx, cacheKey)
	
	return user, nil
}

func (s *UserService) Login(ctx context.Context, req LoginRequest) (*LoginResponse, error) {
	user, err := s.repo.GetByUsername(ctx, req.Username)
	if err != nil {
		s.metrics.LoginAttempts.WithLabelValues("failure").Inc()
		return nil, fmt.Errorf("invalid credentials")
	}
	
	if !user.Status.IsActive() {
		s.metrics.LoginAttempts.WithLabelValues("inactive").Inc()
		return nil, fmt.Errorf("account is not active")
	}
	
	if !verifyPassword(req.Password, user.Password) {
		s.metrics.LoginAttempts.WithLabelValues("failure").Inc()
		return nil, fmt.Errorf("invalid credentials")
	}
	
	// Generate JWT token
	expiresAt := time.Now().Add(24 * time.Hour)
	claims := &JWTClaims{
		UserID:   user.ID,
		Username: user.Username,
		Role:     user.Role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(expiresAt),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			Issuer:    "microservice-api",
		},
	}
	
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString(s.jwtSecret)
	if err != nil {
		return nil, fmt.Errorf("failed to generate token")
	}
	
	// Store session
	session := &Session{
		ID:        generateSessionID(),
		UserID:    user.ID,
		Token:     tokenString,
		ExpiresAt: expiresAt,
	}
	
	if err := s.sessionRepo.Create(ctx, session); err != nil {
		s.logger.Warn("Failed to store session", zap.Error(err))
	}
	
	s.metrics.LoginAttempts.WithLabelValues("success").Inc()
	
	return &LoginResponse{
		Token:     tokenString,
		ExpiresAt: expiresAt,
		User:      *user,
	}, nil
}

// HTTP Handlers
type Handler struct {
	userService *UserService
	logger      *zap.Logger
	metrics     *Metrics
}

func NewHandler(userService *UserService, logger *zap.Logger, metrics *Metrics) *Handler {
	return &Handler{
		userService: userService,
		logger:      logger,
		metrics:     metrics,
	}
}

func (h *Handler) CreateUser(c *gin.Context) {
	var req CreateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		h.respondWithError(c, http.StatusBadRequest, "Invalid request", err)
		return
	}
	
	user, err := h.userService.CreateUser(c.Request.Context(), req)
	if err != nil {
		h.respondWithError(c, http.StatusConflict, "Failed to create user", err)
		return
	}
	
	c.JSON(http.StatusCreated, user)
}

func (h *Handler) GetUser(c *gin.Context) {
	idParam := c.Param("id")
	id, err := strconv.ParseUint(idParam, 10, 32)
	if err != nil {
		h.respondWithError(c, http.StatusBadRequest, "Invalid user ID", err)
		return
	}
	
	user, err := h.userService.GetUser(c.Request.Context(), uint(id))
	if err != nil {
		h.respondWithError(c, http.StatusNotFound, "User not found", err)
		return
	}
	
	c.JSON(http.StatusOK, user)
}

func (h *Handler) UpdateUser(c *gin.Context) {
	idParam := c.Param("id")
	id, err := strconv.ParseUint(idParam, 10, 32)
	if err != nil {
		h.respondWithError(c, http.StatusBadRequest, "Invalid user ID", err)
		return
	}
	
	var req UpdateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		h.respondWithError(c, http.StatusBadRequest, "Invalid request", err)
		return
	}
	
	user, err := h.userService.UpdateUser(c.Request.Context(), uint(id), req)
	if err != nil {
		h.respondWithError(c, http.StatusNotFound, "Failed to update user", err)
		return
	}
	
	c.JSON(http.StatusOK, user)
}

func (h *Handler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		h.respondWithError(c, http.StatusBadRequest, "Invalid request", err)
		return
	}
	
	response, err := h.userService.Login(c.Request.Context(), req)
	if err != nil {
		h.respondWithError(c, http.StatusUnauthorized, "Login failed", err)
		return
	}
	
	c.JSON(http.StatusOK, response)
}

func (h *Handler) respondWithError(c *gin.Context, status int, message string, err error) {
	h.logger.Error(message, zap.Error(err))
	
	response := ErrorResponse{
		Error:     http.StatusText(status),
		Message:   message,
		Timestamp: time.Now(),
	}
	
	c.JSON(status, response)
}

// Metrics
type Metrics struct {
	UsersCreated   prometheus.Counter
	LoginAttempts  *prometheus.CounterVec
	CacheHits      prometheus.Counter
	CacheMisses    prometheus.Counter
	RequestDuration *prometheus.HistogramVec
}

func NewMetrics() *Metrics {
	return &Metrics{
		UsersCreated: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "users_created_total",
			Help: "Total number of users created",
		}),
		LoginAttempts: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "login_attempts_total",
			Help: "Total number of login attempts",
		}, []string{"status"}),
		CacheHits: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "cache_hits_total",
			Help: "Total number of cache hits",
		}),
		CacheMisses: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "cache_misses_total",
			Help: "Total number of cache misses",
		}),
		RequestDuration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "request_duration_seconds",
			Help:    "Request duration in seconds",
			Buckets: prometheus.DefBuckets,
		}, []string{"method", "endpoint", "status"}),
	}
}

func (m *Metrics) Register() {
	prometheus.MustRegister(
		m.UsersCreated,
		m.LoginAttempts,
		m.CacheHits,
		m.CacheMisses,
		m.RequestDuration,
	)
}

// Middleware
func LoggingMiddleware(logger *zap.Logger) gin.HandlerFunc {
	return gin.LoggerWithConfig(gin.LoggerConfig{
		Formatter: func(param gin.LogFormatterParams) string {
			logger.Info("HTTP Request",
				zap.String("method", param.Method),
				zap.String("path", param.Path),
				zap.Int("status", param.StatusCode),
				zap.Duration("latency", param.Latency),
			)
			return ""
		},
	})
}

func MetricsMiddleware(metrics *Metrics) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		
		c.Next()
		
		duration := time.Since(start)
		status := strconv.Itoa(c.Writer.Status())
		
		metrics.RequestDuration.WithLabelValues(
			c.Request.Method,
			c.FullPath(),
			status,
		).Observe(duration.Seconds())
	}
}

func AuthMiddleware(jwtSecret []byte) gin.HandlerFunc {
	return func(c *gin.Context) {
		tokenString := c.GetHeader("Authorization")
		if tokenString == "" {
			c.JSON(http.StatusUnauthorized, ErrorResponse{
				Error:     "Unauthorized",
				Message:   "Missing authorization header",
				Timestamp: time.Now(),
			})
			c.Abort()
			return
		}
		
		// Remove "Bearer " prefix if present
		if len(tokenString) > 7 && tokenString[:7] == "Bearer " {
			tokenString = tokenString[7:]
		}
		
		token, err := jwt.ParseWithClaims(tokenString, &JWTClaims{}, func(token *jwt.Token) (interface{}, error) {
			return jwtSecret, nil
		})
		
		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, ErrorResponse{
				Error:     "Unauthorized",
				Message:   "Invalid token",
				Timestamp: time.Now(),
			})
			c.Abort()
			return
		}
		
		claims, ok := token.Claims.(*JWTClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, ErrorResponse{
				Error:     "Unauthorized", 
				Message:   "Invalid token claims",
				Timestamp: time.Now(),
			})
			c.Abort()
			return
		}
		
		c.Set("user_id", claims.UserID)
		c.Set("username", claims.Username)
		c.Set("role", claims.Role)
		c.Next()
	}
}

// Utility functions
func hashPassword(password string) (string, error) {
	// Implementation would use bcrypt or similar
	return "hashed_" + password, nil
}

func verifyPassword(password, hash string) bool {
	// Implementation would use bcrypt or similar
	return hash == "hashed_"+password
}

func generateSessionID() string {
	// Implementation would generate a secure session ID
	return fmt.Sprintf("session_%d", time.Now().UnixNano())
}

// Main application
func main() {
	// Initialize logger
	logger, _ := zap.NewProduction()
	defer logger.Sync()
	
	// Load configuration
	config := loadConfig()
	
	// Initialize database
	db, err := initDatabase(config.Database)
	if err != nil {
		logger.Fatal("Failed to initialize database", zap.Error(err))
	}
	
	// Initialize Redis
	redisClient := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", config.Redis.Host, config.Redis.Port),
		Password: config.Redis.Password,
		DB:       config.Redis.DB,
	})
	
	// Initialize metrics
	metrics := NewMetrics()
	metrics.Register()
	
	// Initialize repositories
	userRepo := NewUserRepository(db)
	
	// Initialize services
	userService := NewUserService(
		userRepo,
		nil, // orderRepo would be initialized here
		nil, // sessionRepo would be initialized here
		redisClient,
		[]byte(config.JWT.SecretKey),
		logger,
		metrics,
	)
	
	// Initialize handlers
	handler := NewHandler(userService, logger, metrics)
	
	// Setup routes
	router := setupRoutes(handler, config, logger, metrics)
	
	// Start server
	server := &http.Server{
		Addr:         ":" + config.Server.Port,
		Handler:      router,
		ReadTimeout:  config.Server.ReadTimeout,
		WriteTimeout: config.Server.WriteTimeout,
		IdleTimeout:  config.Server.IdleTimeout,
	}
	
	logger.Info("Starting server", zap.String("port", config.Server.Port))
	log.Fatal(server.ListenAndServe())
}

func loadConfig() Config {
	// Implementation would load from file/env
	return Config{
		Server: ServerConfig{
			Port:         "8080",
			ReadTimeout:  30 * time.Second,
			WriteTimeout: 30 * time.Second,
			IdleTimeout:  120 * time.Second,
		},
		JWT: JWTConfig{
			SecretKey:      os.Getenv("JWT_SECRET"),
			ExpirationTime: 24 * time.Hour,
			Issuer:        "microservice-api",
		},
	}
}

func initDatabase(config DatabaseConfig) (*gorm.DB, error) {
	dsn := fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		config.Host, config.Port, config.User, config.Password, config.DBName, config.SSLMode)
	
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, err
	}
	
	// Auto-migrate tables
	err = db.AutoMigrate(&User{}, &Profile{}, &Order{}, &OrderItem{}, &Session{})
	if err != nil {
		return nil, err
	}
	
	return db, nil
}

func setupRoutes(handler *Handler, config Config, logger *zap.Logger, metrics *Metrics) *gin.Engine {
	router := gin.New()
	router.Use(LoggingMiddleware(logger))
	router.Use(MetricsMiddleware(metrics))
	
	// Public routes
	public := router.Group("/api/v1")
	{
		public.POST("/users", handler.CreateUser)
		public.POST("/login", handler.Login)
	}
	
	// Protected routes
	protected := router.Group("/api/v1")
	protected.Use(AuthMiddleware([]byte(config.JWT.SecretKey)))
	{
		protected.GET("/users/:id", handler.GetUser)
		protected.PUT("/users/:id", handler.UpdateUser)
	}
	
	// Health check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})
	
	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))
	
	return router
}
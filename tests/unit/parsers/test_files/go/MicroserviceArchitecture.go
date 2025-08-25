// Package main demonstrates a complex Go microservice architecture
// with modern Go idioms, generics, interfaces, and error handling patterns
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/mux"
	"github.com/lib/pq"
	"go.uber.org/zap"
)

// Generic constraints and interfaces
type Comparable[T any] interface {
	CompareTo(other T) int
}

type Serializable interface {
	Marshal() ([]byte, error)
	Unmarshal(data []byte) error
}

// Complex generic interfaces with type constraints
type Repository[T any, K comparable] interface {
	FindByID(ctx context.Context, id K) (*T, error)
	FindAll(ctx context.Context, limit, offset int) ([]T, error)
	Create(ctx context.Context, entity *T) error
	Update(ctx context.Context, id K, entity *T) error
	Delete(ctx context.Context, id K) error
}

type CacheManager[K comparable, V any] interface {
	Get(key K) (V, bool)
	Set(key K, value V, ttl time.Duration) error
	Delete(key K) error
	Clear() error
}

// Domain models with complex struct tags and embedded types
type BaseEntity struct {
	ID        int64     `json:"id" db:"id"`
	CreatedAt time.Time `json:"created_at" db:"created_at"`
	UpdatedAt time.Time `json:"updated_at" db:"updated_at"`
	Version   int       `json:"version" db:"version"`
}

type User struct {
	BaseEntity
	Email     string     `json:"email" db:"email" validate:"required,email"`
	Username  string     `json:"username" db:"username" validate:"required,min=3,max=50"`
	FirstName string     `json:"first_name" db:"first_name" validate:"required"`
	LastName  string     `json:"last_name" db:"last_name" validate:"required"`
	IsActive  bool       `json:"is_active" db:"is_active"`
	LastLogin *time.Time `json:"last_login,omitempty" db:"last_login"`
	Profile   *Profile   `json:"profile,omitempty"`
	Settings  UserSettings `json:"settings"`
}

type Profile struct {
	UserID      int64  `json:"user_id" db:"user_id"`
	Bio         string `json:"bio" db:"bio"`
	AvatarURL   string `json:"avatar_url" db:"avatar_url"`
	Website     string `json:"website" db:"website"`
	Location    string `json:"location" db:"location"`
	DateOfBirth *time.Time `json:"date_of_birth" db:"date_of_birth"`
}

type UserSettings struct {
	Theme         string            `json:"theme" db:"theme"`
	Language      string            `json:"language" db:"language"`
	Timezone      string            `json:"timezone" db:"timezone"`
	Notifications NotificationSettings `json:"notifications"`
	Privacy       PrivacySettings   `json:"privacy"`
	Preferences   map[string]interface{} `json:"preferences" db:"preferences"`
}

type NotificationSettings struct {
	Email    bool `json:"email" db:"email_notifications"`
	Push     bool `json:"push" db:"push_notifications"`
	SMS      bool `json:"sms" db:"sms_notifications"`
	InApp    bool `json:"in_app" db:"in_app_notifications"`
}

type PrivacySettings struct {
	ProfileVisibility string `json:"profile_visibility" db:"profile_visibility"`
	ShowEmail        bool   `json:"show_email" db:"show_email"`
	ShowLastSeen     bool   `json:"show_last_seen" db:"show_last_seen"`
}

// Generic response wrapper with error handling
type APIResponse[T any] struct {
	Success    bool                   `json:"success"`
	Data       *T                     `json:"data,omitempty"`
	Error      *APIError              `json:"error,omitempty"`
	Pagination *PaginationInfo        `json:"pagination,omitempty"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
}

type APIError struct {
	Code    string            `json:"code"`
	Message string            `json:"message"`
	Details map[string]string `json:"details,omitempty"`
}

type PaginationInfo struct {
	Page       int   `json:"page"`
	Limit      int   `json:"limit"`
	Total      int64 `json:"total"`
	TotalPages int   `json:"total_pages"`
	HasNext    bool  `json:"has_next"`
	HasPrev    bool  `json:"has_prev"`
}

// Complex service interfaces with generic constraints
type UserService interface {
	GetUser(ctx context.Context, id int64) (*User, error)
	GetUsers(ctx context.Context, filter UserFilter) (*PaginatedResult[User], error)
	CreateUser(ctx context.Context, user *CreateUserRequest) (*User, error)
	UpdateUser(ctx context.Context, id int64, user *UpdateUserRequest) (*User, error)
	DeleteUser(ctx context.Context, id int64) error
	ActivateUser(ctx context.Context, id int64) error
	DeactivateUser(ctx context.Context, id int64) error
}

type EventPublisher interface {
	Publish(ctx context.Context, event Event) error
	PublishAsync(ctx context.Context, event Event) <-chan error
	Subscribe(eventType string, handler EventHandler) error
	Unsubscribe(eventType string, handler EventHandler) error
}

// Generic filter and pagination types
type UserFilter struct {
	Email    *string `json:"email"`
	Username *string `json:"username"`
	IsActive *bool   `json:"is_active"`
	Search   *string `json:"search"`
}

type PaginatedResult[T any] struct {
	Items      []T            `json:"items"`
	Pagination PaginationInfo `json:"pagination"`
}

// Complex service implementation with embedded interfaces
type userService struct {
	repo      Repository[User, int64]
	cache     CacheManager[int64, *User]
	publisher EventPublisher
	logger    *zap.Logger
	validator Validator
	mu        sync.RWMutex
	metrics   *ServiceMetrics
}

// Constructor with functional options pattern
type UserServiceOption func(*userService)

func WithCache[K comparable, V any](cache CacheManager[K, V]) UserServiceOption {
	return func(s *userService) {
		if c, ok := any(cache).(CacheManager[int64, *User]); ok {
			s.cache = c
		}
	}
}

func WithEventPublisher(publisher EventPublisher) UserServiceOption {
	return func(s *userService) {
		s.publisher = publisher
	}
}

func WithLogger(logger *zap.Logger) UserServiceOption {
	return func(s *userService) {
		s.logger = logger
	}
}

func NewUserService(
	repo Repository[User, int64],
	validator Validator,
	options ...UserServiceOption,
) UserService {
	service := &userService{
		repo:      repo,
		validator: validator,
		logger:    zap.NewNop(),
		metrics:   NewServiceMetrics("user_service"),
	}

	for _, option := range options {
		option(service)
	}

	return service
}

// Complex method implementations with error handling
func (s *userService) GetUser(ctx context.Context, id int64) (*User, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	timer := s.metrics.StartTimer("get_user")
	defer timer.Stop()

	// Try cache first
	if s.cache != nil {
		if user, found := s.cache.Get(id); found {
			s.metrics.IncrementCounter("cache_hits")
			return user, nil
		}
		s.metrics.IncrementCounter("cache_misses")
	}

	user, err := s.repo.FindByID(ctx, id)
	if err != nil {
		s.logger.Error("Failed to get user", zap.Int64("user_id", id), zap.Error(err))
		s.metrics.IncrementCounter("errors")
		return nil, fmt.Errorf("failed to get user: %w", err)
	}

	if user == nil {
		return nil, ErrUserNotFound
	}

	// Cache the result
	if s.cache != nil {
		if err := s.cache.Set(id, user, 5*time.Minute); err != nil {
			s.logger.Warn("Failed to cache user", zap.Int64("user_id", id), zap.Error(err))
		}
	}

	return user, nil
}

func (s *userService) GetUsers(ctx context.Context, filter UserFilter) (*PaginatedResult[User], error) {
	timer := s.metrics.StartTimer("get_users")
	defer timer.Stop()

	// Implementation would include complex filtering logic
	users, err := s.repo.FindAll(ctx, 50, 0) // Simplified
	if err != nil {
		s.logger.Error("Failed to get users", zap.Error(err))
		s.metrics.IncrementCounter("errors")
		return nil, fmt.Errorf("failed to get users: %w", err)
	}

	return &PaginatedResult[User]{
		Items: users,
		Pagination: PaginationInfo{
			Page:       1,
			Limit:      50,
			Total:      int64(len(users)),
			TotalPages: 1,
			HasNext:    false,
			HasPrev:    false,
		},
	}, nil
}

func (s *userService) CreateUser(ctx context.Context, req *CreateUserRequest) (*User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	timer := s.metrics.StartTimer("create_user")
	defer timer.Stop()

	// Validate request
	if err := s.validator.Validate(req); err != nil {
		return nil, fmt.Errorf("validation failed: %w", err)
	}

	user := &User{
		BaseEntity: BaseEntity{
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
			Version:   1,
		},
		Email:     req.Email,
		Username:  req.Username,
		FirstName: req.FirstName,
		LastName:  req.LastName,
		IsActive:  true,
		Settings: UserSettings{
			Theme:    "light",
			Language: "en",
			Timezone: "UTC",
			Notifications: NotificationSettings{
				Email: true,
				Push:  true,
				SMS:   false,
				InApp: true,
			},
			Privacy: PrivacySettings{
				ProfileVisibility: "public",
				ShowEmail:        false,
				ShowLastSeen:     true,
			},
			Preferences: make(map[string]interface{}),
		},
	}

	if err := s.repo.Create(ctx, user); err != nil {
		s.logger.Error("Failed to create user", zap.Error(err))
		s.metrics.IncrementCounter("errors")
		return nil, fmt.Errorf("failed to create user: %w", err)
	}

	// Publish user created event
	if s.publisher != nil {
		event := UserCreatedEvent{
			BaseEvent: BaseEvent{
				ID:        generateEventID(),
				Type:      "user.created",
				Timestamp: time.Now(),
			},
			UserID: user.ID,
			Email:  user.Email,
		}

		if err := s.publisher.Publish(ctx, event); err != nil {
			s.logger.Warn("Failed to publish user created event", zap.Error(err))
		}
	}

	s.metrics.IncrementCounter("users_created")
	return user, nil
}

// Generic event system
type Event interface {
	GetID() string
	GetType() string
	GetTimestamp() time.Time
	GetPayload() interface{}
}

type BaseEvent struct {
	ID        string    `json:"id"`
	Type      string    `json:"type"`
	Timestamp time.Time `json:"timestamp"`
}

func (e BaseEvent) GetID() string        { return e.ID }
func (e BaseEvent) GetType() string      { return e.Type }
func (e BaseEvent) GetTimestamp() time.Time { return e.Timestamp }

type UserCreatedEvent struct {
	BaseEvent
	UserID int64  `json:"user_id"`
	Email  string `json:"email"`
}

func (e UserCreatedEvent) GetPayload() interface{} {
	return map[string]interface{}{
		"user_id": e.UserID,
		"email":   e.Email,
	}
}

type EventHandler func(ctx context.Context, event Event) error

// Complex HTTP handlers with middleware
type HTTPServer struct {
	service UserService
	logger  *zap.Logger
	router  *mux.Router
}

func NewHTTPServer(service UserService, logger *zap.Logger) *HTTPServer {
	server := &HTTPServer{
		service: service,
		logger:  logger,
		router:  mux.NewRouter(),
	}

	server.setupRoutes()
	return server
}

func (s *HTTPServer) setupRoutes() {
	api := s.router.PathPrefix("/api/v1").Subrouter()
	
	// Middleware
	api.Use(s.loggingMiddleware)
	api.Use(s.recoveryMiddleware)
	api.Use(s.corsMiddleware)

	// User routes
	users := api.PathPrefix("/users").Subrouter()
	users.HandleFunc("", s.getUsers).Methods("GET")
	users.HandleFunc("", s.createUser).Methods("POST")
	users.HandleFunc("/{id:[0-9]+}", s.getUser).Methods("GET")
	users.HandleFunc("/{id:[0-9]+}", s.updateUser).Methods("PUT")
	users.HandleFunc("/{id:[0-9]+}", s.deleteUser).Methods("DELETE")
}

// Complex middleware implementations
func (s *HTTPServer) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap response writer to capture status code
		wrapper := &responseWriter{
			ResponseWriter: w,
			statusCode:     http.StatusOK,
		}

		next.ServeHTTP(wrapper, r)

		s.logger.Info("HTTP Request",
			zap.String("method", r.Method),
			zap.String("path", r.URL.Path),
			zap.Int("status", wrapper.statusCode),
			zap.Duration("duration", time.Since(start)),
			zap.String("remote_addr", r.RemoteAddr),
		)
	})
}

func (s *HTTPServer) recoveryMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if err := recover(); err != nil {
				s.logger.Error("Panic recovered",
					zap.Any("error", err),
					zap.String("path", r.URL.Path),
				)

				response := APIResponse[interface{}]{
					Success: false,
					Error: &APIError{
						Code:    "internal_error",
						Message: "Internal server error",
					},
				}

				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				json.NewEncoder(w).Encode(response)
			}
		}()

		next.ServeHTTP(w, r)
	})
}

func (s *HTTPServer) corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// Complex handler implementations with error handling
func (s *HTTPServer) getUser(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	userID, err := parseID(vars["id"])
	if err != nil {
		s.writeErrorResponse(w, http.StatusBadRequest, "invalid_id", "Invalid user ID")
		return
	}

	user, err := s.service.GetUser(r.Context(), userID)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			s.writeErrorResponse(w, http.StatusNotFound, "user_not_found", "User not found")
			return
		}

		s.logger.Error("Failed to get user", zap.Error(err))
		s.writeErrorResponse(w, http.StatusInternalServerError, "internal_error", "Internal server error")
		return
	}

	s.writeSuccessResponse(w, user)
}

func (s *HTTPServer) createUser(w http.ResponseWriter, r *http.Request) {
	var req CreateUserRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		s.writeErrorResponse(w, http.StatusBadRequest, "invalid_json", "Invalid JSON")
		return
	}

	user, err := s.service.CreateUser(r.Context(), &req)
	if err != nil {
		if errors.Is(err, ErrValidationFailed) {
			s.writeErrorResponse(w, http.StatusBadRequest, "validation_failed", err.Error())
			return
		}

		s.logger.Error("Failed to create user", zap.Error(err))
		s.writeErrorResponse(w, http.StatusInternalServerError, "internal_error", "Internal server error")
		return
	}

	s.writeSuccessResponse(w, user)
}

// Generic helper methods
func (s *HTTPServer) writeSuccessResponse(w http.ResponseWriter, data interface{}) {
	response := APIResponse[interface{}]{
		Success: true,
		Data:    &data,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func (s *HTTPServer) writeErrorResponse(w http.ResponseWriter, status int, code, message string) {
	response := APIResponse[interface{}]{
		Success: false,
		Error: &APIError{
			Code:    code,
			Message: message,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(response)
}

// Complex application with graceful shutdown
type Application struct {
	server   *HTTPServer
	database *sql.DB
	logger   *zap.Logger
	config   *Config
}

type Config struct {
	Port        int    `json:"port" env:"PORT" default:"8080"`
	DatabaseURL string `json:"database_url" env:"DATABASE_URL"`
	LogLevel    string `json:"log_level" env:"LOG_LEVEL" default:"info"`
	Environment string `json:"environment" env:"ENVIRONMENT" default:"development"`
}

func NewApplication(config *Config) (*Application, error) {
	// Setup logger
	logger, err := setupLogger(config.LogLevel)
	if err != nil {
		return nil, fmt.Errorf("failed to setup logger: %w", err)
	}

	// Setup database
	db, err := sql.Open("postgres", config.DatabaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Create services
	userRepo := NewUserRepository(db)
	validator := NewValidator()
	cache := NewMemoryCache[int64, *User]()
	
	userService := NewUserService(
		userRepo,
		validator,
		WithCache(cache),
		WithLogger(logger),
	)

	// Create HTTP server
	httpServer := NewHTTPServer(userService, logger)

	return &Application{
		server:   httpServer,
		database: db,
		logger:   logger,
		config:   config,
	}, nil
}

func (app *Application) Start(ctx context.Context) error {
	// Start HTTP server
	server := &http.Server{
		Addr:    fmt.Sprintf(":%d", app.config.Port),
		Handler: app.server.router,
	}

	// Graceful shutdown
	go func() {
		<-ctx.Done()
		
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		if err := server.Shutdown(shutdownCtx); err != nil {
			app.logger.Error("Server shutdown error", zap.Error(err))
		}

		if err := app.database.Close(); err != nil {
			app.logger.Error("Database close error", zap.Error(err))
		}
	}()

	app.logger.Info("Starting server", zap.Int("port", app.config.Port))
	return server.ListenAndServe()
}

func main() {
	config := &Config{
		Port:        8080,
		DatabaseURL: os.Getenv("DATABASE_URL"),
		LogLevel:    "info",
		Environment: "development",
	}

	app, err := NewApplication(config)
	if err != nil {
		log.Fatal("Failed to create application:", err)
	}

	// Setup signal handling
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		
		log.Println("Shutting down gracefully...")
		cancel()
	}()

	if err := app.Start(ctx); err != nil && err != http.ErrServerClosed {
		log.Fatal("Server failed to start:", err)
	}

	log.Println("Server stopped")
}

// Custom errors
var (
	ErrUserNotFound      = errors.New("user not found")
	ErrValidationFailed  = errors.New("validation failed")
	ErrInternalError     = errors.New("internal error")
)

// Additional types and interfaces (simplified implementations would go here)
type CreateUserRequest struct {
	Email     string `json:"email" validate:"required,email"`
	Username  string `json:"username" validate:"required,min=3,max=50"`
	FirstName string `json:"first_name" validate:"required"`
	LastName  string `json:"last_name" validate:"required"`
}

type UpdateUserRequest struct {
	Username  *string `json:"username,omitempty" validate:"omitempty,min=3,max=50"`
	FirstName *string `json:"first_name,omitempty" validate:"omitempty"`
	LastName  *string `json:"last_name,omitempty" validate:"omitempty"`
}

type Validator interface {
	Validate(interface{}) error
}

type ServiceMetrics struct {
	name     string
	counters map[string]int64
	timers   map[string]*Timer
	mu       sync.RWMutex
}

type Timer struct {
	name      string
	startTime time.Time
}

// Placeholder implementations
func NewUserRepository(db *sql.DB) Repository[User, int64] { return nil }
func NewValidator() Validator                             { return nil }
func NewMemoryCache[K comparable, V any]() CacheManager[K, V] { return nil }
func NewServiceMetrics(name string) *ServiceMetrics           { return nil }
func setupLogger(level string) (*zap.Logger, error)          { return zap.NewNop(), nil }
func parseID(s string) (int64, error)                        { return 0, nil }
func generateEventID() string                                 { return "" }

type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}

func (s *ServiceMetrics) StartTimer(name string) *Timer    { return &Timer{} }
func (s *ServiceMetrics) IncrementCounter(name string)     {}
func (t *Timer) Stop()                                      {}
func (s *userService) UpdateUser(ctx context.Context, id int64, req *UpdateUserRequest) (*User, error) { return nil, nil }
func (s *userService) DeleteUser(ctx context.Context, id int64) error { return nil }
func (s *userService) ActivateUser(ctx context.Context, id int64) error { return nil }
func (s *userService) DeactivateUser(ctx context.Context, id int64) error { return nil }
func (s *HTTPServer) getUsers(w http.ResponseWriter, r *http.Request) {}
func (s *HTTPServer) updateUser(w http.ResponseWriter, r *http.Request) {}
func (s *HTTPServer) deleteUser(w http.ResponseWriter, r *http.Request) {}
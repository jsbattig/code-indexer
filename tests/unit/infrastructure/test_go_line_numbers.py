#!/usr/bin/env python3
"""
Comprehensive tests for Go parser line number accuracy.

This test suite verifies that Go semantic parser
reports accurate line numbers that match the actual content boundaries.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.go_parser import GoSemanticParser


class TestGoLineNumbers:
    """Test line number accuracy for Go parser."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        config = IndexingConfig()
        config.chunk_size = 3000  # Large enough to avoid splitting
        config.chunk_overlap = 100
        return config

    @pytest.fixture
    def go_parser(self, config):
        """Create Go parser."""
        return GoSemanticParser(config)

    def _verify_chunk_line_numbers(self, chunk, original_text, file_description=""):
        """
        Verify that a chunk's reported line numbers match its actual content.

        Args:
            chunk: The chunk to verify (SemanticChunk object or dict)
            original_text: The original text the chunk was extracted from
            file_description: Description for error messages
        """
        # Convert to dict if needed
        if hasattr(chunk, "to_dict"):
            chunk_dict = chunk.to_dict()
        else:
            chunk_dict = chunk

        # Get the lines from the original text
        original_lines = original_text.splitlines()

        # Verify line numbers are valid
        assert (
            chunk_dict["line_start"] >= 1
        ), f"{file_description}: line_start must be >= 1, got {chunk_dict['line_start']}"
        assert (
            chunk_dict["line_end"] >= chunk_dict["line_start"]
        ), f"{file_description}: line_end must be >= line_start"
        assert chunk_dict["line_end"] <= len(
            original_lines
        ), f"{file_description}: line_end {chunk_dict['line_end']} exceeds total lines {len(original_lines)}"

        # Extract the expected content based on reported line numbers
        expected_lines = original_lines[
            chunk_dict["line_start"] - 1 : chunk_dict["line_end"]
        ]

        # Get actual chunk content lines
        chunk_content = chunk_dict["text"]
        chunk_lines = chunk_content.splitlines()

        # For basic verification, check first and last non-empty lines
        chunk_first_line = None
        chunk_last_line = None
        expected_first_line = None
        expected_last_line = None

        # Find first non-empty chunk line
        for line in chunk_lines:
            if line.strip():
                chunk_first_line = line.strip()
                break

        # Find last non-empty chunk line
        for line in reversed(chunk_lines):
            if line.strip():
                chunk_last_line = line.strip()
                break

        # Find first non-empty expected line
        for line in expected_lines:
            if line.strip():
                expected_first_line = line.strip()
                break

        # Find last non-empty expected line
        for line in reversed(expected_lines):
            if line.strip():
                expected_last_line = line.strip()
                break

        # Verify the first lines match
        if chunk_first_line and expected_first_line:
            assert chunk_first_line == expected_first_line, (
                f"{file_description}: First line mismatch\n"
                f"Chunk first line: '{chunk_first_line}'\n"
                f"Expected first line: '{expected_first_line}'\n"
                f"Chunk reports lines {chunk_dict['line_start']}-{chunk_dict['line_end']}"
            )

        # Verify the last lines match
        if chunk_last_line and expected_last_line:
            assert chunk_last_line == expected_last_line, (
                f"{file_description}: Last line mismatch\n"
                f"Chunk last line: '{chunk_last_line}'\n"
                f"Expected last line: '{expected_last_line}'\n"
                f"Chunk reports lines {chunk_dict['line_start']}-{chunk_dict['line_end']}"
            )

    def test_go_basic_functions(self, go_parser):
        """Test Go basic function definitions line number accuracy."""
        code = """package main

import (
    "fmt"
    "log"
    "net/http"
)

// Simple function with no parameters
func sayHello() {
    fmt.Println("Hello, World!")
}

// Function with parameters and return value
func add(a, b int) int {
    return a + b
}

// Function with multiple return values
func divide(a, b int) (int, error) {
    if b == 0 {
        return 0, fmt.Errorf("division by zero")
    }
    return a / b, nil
}

// Function with named return values
func calculate(x, y int) (sum, product int) {
    sum = x + y
    product = x * y
    return // naked return
}

// Variadic function
func sum(numbers ...int) int {
    total := 0
    for _, num := range numbers {
        total += num
    }
    return total
}

// Function with slice and map parameters
func processData(items []string, counts map[string]int) {
    for _, item := range items {
        if count, exists := counts[item]; exists {
            fmt.Printf("%s: %d\n", item, count)
        }
    }
}

func main() {
    sayHello()
    result := add(5, 3)
    fmt.Printf("5 + 3 = %d\n", result)
    
    quotient, err := divide(10, 2)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("10 / 2 = %d\n", quotient)
}"""

        chunks = go_parser.chunk(code, "main.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Go basic functions - chunk {i+1}"
            )

    def test_go_structs_and_methods(self, go_parser):
        """Test Go struct definitions and methods line number accuracy."""
        code = """package user

import (
    "fmt"
    "time"
)

// User represents a user in the system
type User struct {
    ID        int       `json:"id"`
    Name      string    `json:"name"`
    Email     string    `json:"email"`
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
    Active    bool      `json:"active"`
}

// NewUser creates a new user instance
func NewUser(name, email string) *User {
    return &User{
        Name:      name,
        Email:     email,
        CreatedAt: time.Now(),
        UpdatedAt: time.Now(),
        Active:    true,
    }
}

// Method with pointer receiver
func (u *User) UpdateEmail(email string) {
    u.Email = email
    u.UpdatedAt = time.Now()
}

// Method with value receiver
func (u User) GetDisplayName() string {
    if u.Name == "" {
        return u.Email
    }
    return u.Name
}

// Method returning multiple values
func (u *User) Validate() (bool, []string) {
    var errors []string
    
    if u.Name == "" {
        errors = append(errors, "name is required")
    }
    
    if u.Email == "" {
        errors = append(errors, "email is required")
    }
    
    if len(u.Email) > 0 && !isValidEmail(u.Email) {
        errors = append(errors, "email format is invalid")
    }
    
    return len(errors) == 0, errors
}

// Private helper function
func isValidEmail(email string) bool {
    // Simple email validation
    return len(email) > 0 && 
           containsChar(email, '@') && 
           containsChar(email, '.')
}

func containsChar(s string, c rune) bool {
    for _, char := range s {
        if char == c {
            return true
        }
    }
    return false
}

// UserRepository manages user data
type UserRepository struct {
    users map[int]*User
    nextID int
}

// NewUserRepository creates a new user repository
func NewUserRepository() *UserRepository {
    return &UserRepository{
        users: make(map[int]*User),
        nextID: 1,
    }
}

// Save stores a user and assigns an ID if needed
func (r *UserRepository) Save(user *User) error {
    if user.ID == 0 {
        user.ID = r.nextID
        r.nextID++
    }
    
    r.users[user.ID] = user
    return nil
}

// FindByID retrieves a user by ID
func (r *UserRepository) FindByID(id int) (*User, bool) {
    user, exists := r.users[id]
    return user, exists
}

// FindAll returns all users
func (r *UserRepository) FindAll() []*User {
    users := make([]*User, 0, len(r.users))
    for _, user := range r.users {
        users = append(users, user)
    }
    return users
}"""

        chunks = go_parser.chunk(code, "user.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Go structs/methods - chunk {i+1}"
            )

    def test_go_interfaces(self, go_parser):
        """Test Go interface definitions line number accuracy."""
        code = """package storage

import (
    "context"
    "io"
)

// Basic interface
type Reader interface {
    Read([]byte) (int, error)
}

// Interface with multiple methods
type Storage interface {
    Store(key string, data []byte) error
    Retrieve(key string) ([]byte, error)
    Delete(key string) error
    List() ([]string, error)
}

// Interface with embedded interfaces
type ReadWriteCloser interface {
    io.Reader
    io.Writer
    io.Closer
}

// Interface with context parameter
type AsyncStorage interface {
    StoreAsync(ctx context.Context, key string, data []byte) error
    RetrieveAsync(ctx context.Context, key string) ([]byte, error)
    DeleteAsync(ctx context.Context, key string) error
}

// Generic interface (Go 1.18+)
type Comparable[T comparable] interface {
    Compare(other T) int
    Equal(other T) bool
}

// Interface with type constraints
type Numeric interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64 |
    ~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 |
    ~float32 | ~float64
}

// Complex interface with methods and embedded types
type AdvancedStorage interface {
    Storage  // Embedded interface
    
    // Batch operations
    StoreBatch(items map[string][]byte) error
    RetrieveBatch(keys []string) (map[string][]byte, error)
    
    // Metadata operations
    GetMetadata(key string) (map[string]string, error)
    SetMetadata(key string, metadata map[string]string) error
    
    // Transaction support
    BeginTransaction() Transaction
}

// Transaction interface for advanced storage
type Transaction interface {
    Store(key string, data []byte) error
    Delete(key string) error
    Commit() error
    Rollback() error
}

// Empty interface (any type)
type Any interface{}

// Interface with function types
type EventHandler interface {
    HandleEvent(eventType string, handler func(interface{}) error)
    RemoveHandler(eventType string)
    TriggerEvent(eventType string, data interface{}) error
}"""

        chunks = go_parser.chunk(code, "interfaces.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(chunk, code, f"Go interfaces - chunk {i+1}")

    def test_go_type_definitions(self, go_parser):
        """Test Go type definitions and aliases line number accuracy."""
        code = """package types

import (
    "fmt"
    "time"
)

// Basic type alias
type UserID int

// Type alias for built-in type
type Email string

// Function type
type Handler func(request Request) Response

// Function type with multiple parameters and returns
type Processor func(input []byte, config Config) ([]byte, error)

// Generic function type (Go 1.18+)
type Mapper[T, R any] func(T) R

// Type alias for slice
type UserList []User

// Type alias for map
type UserCache map[UserID]*User

// Type alias for channel
type MessageChannel chan string

// Complex type with interface
type Validator interface {
    Validate(value interface{}) error
}

// Struct type with validation
type Config struct {
    Host     string    `json:"host" validate:"required"`
    Port     int       `json:"port" validate:"min=1,max=65535"`
    Timeout  time.Duration `json:"timeout"`
    Debug    bool      `json:"debug"`
    Features []string  `json:"features"`
}

// Method on type alias
func (e Email) IsValid() bool {
    return len(e) > 0 && 
           containsAt(string(e)) && 
           containsDot(string(e))
}

func (e Email) Domain() string {
    email := string(e)
    atIndex := -1
    for i, c := range email {
        if c == '@' {
            atIndex = i
            break
        }
    }
    if atIndex >= 0 && atIndex < len(email)-1 {
        return email[atIndex+1:]
    }
    return ""
}

// Method on function type
func (h Handler) WithLogging() Handler {
    return func(request Request) Response {
        fmt.Printf("Handling request: %+v\n", request)
        response := h(request)
        fmt.Printf("Response: %+v\n", response)
        return response
    }
}

// Generic type definition
type Container[T any] struct {
    items []T
    mutex sync.RWMutex
}

// Methods on generic type
func (c *Container[T]) Add(item T) {
    c.mutex.Lock()
    defer c.mutex.Unlock()
    c.items = append(c.items, item)
}

func (c *Container[T]) Get(index int) (T, bool) {
    c.mutex.RLock()
    defer c.mutex.RUnlock()
    
    var zero T
    if index < 0 || index >= len(c.items) {
        return zero, false
    }
    return c.items[index], true
}

func (c *Container[T]) Len() int {
    c.mutex.RLock()
    defer c.mutex.RUnlock()
    return len(c.items)
}

// Helper functions
func containsAt(s string) bool {
    for _, c := range s {
        if c == '@' {
            return true
        }
    }
    return false
}

func containsDot(s string) bool {
    for _, c := range s {
        if c == '.' {
            return true
        }
    }
    return false
}

// Type for demonstration
type Request struct {
    ID     string
    Method string
    Path   string
    Body   []byte
}

type Response struct {
    Status int
    Body   []byte
    Headers map[string]string
}"""

        chunks = go_parser.chunk(code, "types.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Go type definitions - chunk {i+1}"
            )

    def test_go_constants_and_variables(self, go_parser):
        """Test Go constant and variable declarations line number accuracy."""
        code = """package config

import (
    "os"
    "time"
)

// Single constants
const AppName = "MyApplication"
const Version = "1.0.0"

// Constant block
const (
    MaxRetries    = 3
    RetryDelay    = time.Second * 2
    DefaultPort   = 8080
    DefaultHost   = "localhost"
    
    // Iota constants
    StatusUnknown = iota
    StatusPending
    StatusRunning
    StatusCompleted
    StatusFailed
)

// Typed constants
const (
    KB int64 = 1024
    MB       = KB * 1024
    GB       = MB * 1024
    TB       = GB * 1024
)

// String constants with expressions
const (
    DatabaseURL = "postgres://localhost:5432/myapp"
    CacheKey    = AppName + ":cache:"
    LogFormat   = "[%s] %s: %s\n"
)

// Single variables
var GlobalConfig *Config
var StartTime time.Time

// Variable block with initialization
var (
    httpClient = &http.Client{
        Timeout: 30 * time.Second,
    }
    
    logger = log.New(os.Stdout, "APP: ", log.LstdFlags)
    
    // Variables with types
    configPath   string
    debugMode    bool
    maxWorkers   int = 10
    
    // Slice and map variables
    allowedHosts []string
    userSessions map[string]*Session
)

// Variables with function calls
var (
    currentUser = getCurrentUser()
    systemInfo  = getSystemInfo()
    environment = os.Getenv("APP_ENV")
)

// Init function
func init() {
    StartTime = time.Now()
    
    if environment == "" {
        environment = "development"
    }
    
    // Initialize maps and slices
    allowedHosts = []string{"localhost", "127.0.0.1"}
    userSessions = make(map[string]*Session)
    
    // Load configuration
    loadConfiguration()
}

// Helper functions for variable initialization
func getCurrentUser() string {
    if user := os.Getenv("USER"); user != "" {
        return user
    }
    return "unknown"
}

func getSystemInfo() map[string]interface{} {
    return map[string]interface{}{
        "os":   runtime.GOOS,
        "arch": runtime.GOARCH,
        "cpus": runtime.NumCPU(),
    }
}

func loadConfiguration() {
    configPath = os.Getenv("CONFIG_PATH")
    if configPath == "" {
        configPath = "./config.yaml"
    }
    
    if os.Getenv("DEBUG") == "true" {
        debugMode = true
    }
}

// Configuration struct
type Config struct {
    Database DatabaseConfig `yaml:"database"`
    Server   ServerConfig   `yaml:"server"`
    Cache    CacheConfig    `yaml:"cache"`
    Logging  LoggingConfig  `yaml:"logging"`
}

type DatabaseConfig struct {
    Host     string `yaml:"host"`
    Port     int    `yaml:"port"`
    Database string `yaml:"database"`
    Username string `yaml:"username"`
    Password string `yaml:"password"`
}

type ServerConfig struct {
    Host         string        `yaml:"host"`
    Port         int           `yaml:"port"`
    ReadTimeout  time.Duration `yaml:"read_timeout"`
    WriteTimeout time.Duration `yaml:"write_timeout"`
    IdleTimeout  time.Duration `yaml:"idle_timeout"`
}

type CacheConfig struct {
    Enabled bool          `yaml:"enabled"`
    TTL     time.Duration `yaml:"ttl"`
    MaxSize int           `yaml:"max_size"`
}

type LoggingConfig struct {
    Level  string `yaml:"level"`
    Format string `yaml:"format"`
    Output string `yaml:"output"`
}

type Session struct {
    ID        string
    UserID    string
    CreatedAt time.Time
    ExpiresAt time.Time
    Data      map[string]interface{}
}"""

        chunks = go_parser.chunk(code, "config.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Go constants/variables - chunk {i+1}"
            )

    def test_go_generics(self, go_parser):
        """Test Go generic constructs line number accuracy (Go 1.18+)."""
        code = """package generics

import (
    "fmt"
    "sort"
)

// Generic function with type constraint
func Max[T comparable](a, b T) T {
    if a > b {
        return a
    }
    return b
}

// Generic function with multiple type parameters
func Map[T, R any](slice []T, fn func(T) R) []R {
    result := make([]R, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}

// Generic function with constraint interface
func Sort[T constraints.Ordered](slice []T) {
    sort.Slice(slice, func(i, j int) bool {
        return slice[i] < slice[j]
    })
}

// Generic struct with multiple type parameters
type Pair[T, U any] struct {
    First  T
    Second U
}

// Methods on generic struct
func (p Pair[T, U]) String() string {
    return fmt.Sprintf("(%v, %v)", p.First, p.Second)
}

func (p Pair[T, U]) Swap() Pair[U, T] {
    return Pair[U, T]{
        First:  p.Second,
        Second: p.First,
    }
}

// Generic interface
type Comparable[T any] interface {
    CompareTo(other T) int
}

// Generic interface with type constraint
type Numeric[T constraints.Integer | constraints.Float] interface {
    Add(other T) T
    Subtract(other T) T
    Multiply(other T) T
}

// Generic type with constraint
type Stack[T any] struct {
    items []T
}

func NewStack[T any]() *Stack[T] {
    return &Stack[T]{
        items: make([]T, 0),
    }
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    
    index := len(s.items) - 1
    item := s.items[index]
    s.items = s.items[:index]
    return item, true
}

func (s *Stack[T]) Peek() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    return s.items[len(s.items)-1], true
}

func (s *Stack[T]) IsEmpty() bool {
    return len(s.items) == 0
}

func (s *Stack[T]) Size() int {
    return len(s.items)
}

// Generic function with complex constraints
func Reduce[T, R any](slice []T, initial R, fn func(R, T) R) R {
    result := initial
    for _, v := range slice {
        result = fn(result, v)
    }
    return result
}

// Generic type with embedded constraint
type OrderedMap[K comparable, V any] struct {
    keys   []K
    values map[K]V
}

func NewOrderedMap[K comparable, V any]() *OrderedMap[K, V] {
    return &OrderedMap[K, V]{
        keys:   make([]K, 0),
        values: make(map[K]V),
    }
}

func (om *OrderedMap[K, V]) Set(key K, value V) {
    if _, exists := om.values[key]; !exists {
        om.keys = append(om.keys, key)
    }
    om.values[key] = value
}

func (om *OrderedMap[K, V]) Get(key K) (V, bool) {
    value, exists := om.values[key]
    return value, exists
}

func (om *OrderedMap[K, V]) Delete(key K) {
    if _, exists := om.values[key]; exists {
        delete(om.values, key)
        
        // Remove key from ordered list
        for i, k := range om.keys {
            if k == key {
                om.keys = append(om.keys[:i], om.keys[i+1:]...)
                break
            }
        }
    }
}

func (om *OrderedMap[K, V]) Keys() []K {
    result := make([]K, len(om.keys))
    copy(result, om.keys)
    return result
}

func (om *OrderedMap[K, V]) Values() []V {
    result := make([]V, 0, len(om.values))
    for _, key := range om.keys {
        result = append(result, om.values[key])
    }
    return result
}

// Generic constraint interfaces
type constraints struct{}

func (constraints) Ordered() interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64 |
    ~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 | ~uintptr |
    ~float32 | ~float64 |
    ~string
} { return nil }

func (constraints) Integer() interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64 |
    ~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 | ~uintptr
} { return nil }

func (constraints) Float() interface {
    ~float32 | ~float64
} { return nil }"""

        chunks = go_parser.chunk(code, "generics.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(chunk, code, f"Go generics - chunk {i+1}")

    def test_go_complex_structures(self, go_parser):
        """Test Go complex code structures line number accuracy."""
        code = """package server

import (
    "context"
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "sync"
    "time"
)

// Server represents an HTTP server with middleware support
type Server struct {
    mux         *http.ServeMux
    middlewares []Middleware
    config      ServerConfig
    mu          sync.RWMutex
    handlers    map[string]Handler
}

// Middleware type for request processing
type Middleware func(next http.HandlerFunc) http.HandlerFunc

// Handler interface for route handlers
type Handler interface {
    ServeHTTP(w http.ResponseWriter, r *http.Request)
    Path() string
    Method() string
}

// ServerConfig holds server configuration
type ServerConfig struct {
    Host           string        `json:"host"`
    Port           int           `json:"port"`
    ReadTimeout    time.Duration `json:"read_timeout"`
    WriteTimeout   time.Duration `json:"write_timeout"`
    MaxHeaderBytes int           `json:"max_header_bytes"`
}

// NewServer creates a new server instance
func NewServer(config ServerConfig) *Server {
    return &Server{
        mux:         http.NewServeMux(),
        middlewares: make([]Middleware, 0),
        config:      config,
        handlers:    make(map[string]Handler),
    }
}

// Use adds a middleware to the server
func (s *Server) Use(middleware Middleware) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.middlewares = append(s.middlewares, middleware)
}

// Handle registers a handler for a specific route
func (s *Server) Handle(handler Handler) {
    s.mu.Lock()
    defer s.mu.Unlock()
    
    key := fmt.Sprintf("%s:%s", handler.Method(), handler.Path())
    s.handlers[key] = handler
    
    // Wrap handler with all middlewares
    wrappedHandler := s.wrapWithMiddlewares(handler.ServeHTTP)
    s.mux.HandleFunc(handler.Path(), wrappedHandler)
}

// wrapWithMiddlewares applies all middlewares to a handler
func (s *Server) wrapWithMiddlewares(handler http.HandlerFunc) http.HandlerFunc {
    // Apply middlewares in reverse order
    for i := len(s.middlewares) - 1; i >= 0; i-- {
        handler = s.middlewares[i](handler)
    }
    return handler
}

// Start starts the HTTP server
func (s *Server) Start(ctx context.Context) error {
    addr := fmt.Sprintf("%s:%d", s.config.Host, s.config.Port)
    
    server := &http.Server{
        Addr:           addr,
        Handler:        s.mux,
        ReadTimeout:    s.config.ReadTimeout,
        WriteTimeout:   s.config.WriteTimeout,
        MaxHeaderBytes: s.config.MaxHeaderBytes,
    }
    
    // Start server in a goroutine
    errChan := make(chan error, 1)
    go func() {
        log.Printf("Server starting on %s", addr)
        if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            errChan <- err
        }
    }()
    
    // Wait for context cancellation or server error
    select {
    case <-ctx.Done():
        log.Println("Server shutting down...")
        
        // Create shutdown context with timeout
        shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
        defer cancel()
        
        if err := server.Shutdown(shutdownCtx); err != nil {
            log.Printf("Server forced to shutdown: %v", err)
            return err
        }
        
        log.Println("Server shutdown complete")
        return ctx.Err()
        
    case err := <-errChan:
        return err
    }
}

// Middleware implementations

// LoggingMiddleware logs HTTP requests
func LoggingMiddleware(next http.HandlerFunc) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        
        // Create a response writer wrapper to capture status code
        wrapper := &responseWriterWrapper{
            ResponseWriter: w,
            statusCode:     http.StatusOK,
        }
        
        next.ServeHTTP(wrapper, r)
        
        duration := time.Since(start)
        log.Printf(
            "%s %s %d %v %s",
            r.Method,
            r.URL.Path,
            wrapper.statusCode,
            duration,
            r.RemoteAddr,
        )
    }
}

// CORSMiddleware adds CORS headers
func CORSMiddleware(allowedOrigins []string) Middleware {
    return func(next http.HandlerFunc) http.HandlerFunc {
        return func(w http.ResponseWriter, r *http.Request) {
            origin := r.Header.Get("Origin")
            
            // Check if origin is allowed
            for _, allowedOrigin := range allowedOrigins {
                if origin == allowedOrigin || allowedOrigin == "*" {
                    w.Header().Set("Access-Control-Allow-Origin", origin)
                    break
                }
            }
            
            w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
            
            if r.Method == "OPTIONS" {
                w.WriteHeader(http.StatusOK)
                return
            }
            
            next.ServeHTTP(w, r)
        }
    }
}

// AuthMiddleware provides JWT authentication
func AuthMiddleware(secretKey []byte) Middleware {
    return func(next http.HandlerFunc) http.HandlerFunc {
        return func(w http.ResponseWriter, r *http.Request) {
            authHeader := r.Header.Get("Authorization")
            if authHeader == "" {
                http.Error(w, "Authorization header required", http.StatusUnauthorized)
                return
            }
            
            // Simple token validation (in real app, use proper JWT library)
            if !validateToken(authHeader, secretKey) {
                http.Error(w, "Invalid token", http.StatusUnauthorized)
                return
            }
            
            next.ServeHTTP(w, r)
        }
    }
}

// Helper types and functions

type responseWriterWrapper struct {
    http.ResponseWriter
    statusCode int
}

func (w *responseWriterWrapper) WriteHeader(statusCode int) {
    w.statusCode = statusCode
    w.ResponseWriter.WriteHeader(statusCode)
}

func validateToken(token string, secretKey []byte) bool {
    // Simplified token validation
    return len(token) > 10 && len(secretKey) > 0
}

// Example handler implementation
type UserHandler struct {
    userService UserService
}

func NewUserHandler(userService UserService) *UserHandler {
    return &UserHandler{userService: userService}
}

func (h *UserHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    switch r.Method {
    case http.MethodGet:
        h.getUsers(w, r)
    case http.MethodPost:
        h.createUser(w, r)
    default:
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
    }
}

func (h *UserHandler) Path() string {
    return "/api/users"
}

func (h *UserHandler) Method() string {
    return "GET,POST"
}

func (h *UserHandler) getUsers(w http.ResponseWriter, r *http.Request) {
    users, err := h.userService.GetAll()
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(users)
}

func (h *UserHandler) createUser(w http.ResponseWriter, r *http.Request) {
    var user User
    if err := json.NewDecoder(r.Body).Decode(&user); err != nil {
        http.Error(w, "Invalid JSON", http.StatusBadRequest)
        return
    }
    
    if err := h.userService.Create(&user); err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(user)
}

// Service interface and types
type UserService interface {
    GetAll() ([]User, error)
    Create(user *User) error
    GetByID(id string) (*User, error)
    Update(user *User) error
    Delete(id string) error
}

type User struct {
    ID    string `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}"""

        chunks = go_parser.chunk(code, "server.go")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Go complex structures - chunk {i+1}"
            )

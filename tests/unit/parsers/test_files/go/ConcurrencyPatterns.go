package main

import (
	"context"
	"fmt"
	"math/rand"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

// Worker Pool Pattern
type Job struct {
	ID       int
	Data     interface{}
	Priority int
}

type Result struct {
	JobID int
	Value interface{}
	Error error
}

type WorkerPool struct {
	jobs        chan Job
	results     chan Result
	workers     int
	wg          sync.WaitGroup
	ctx         context.Context
	cancel      context.CancelFunc
	done        chan struct{}
	jobsAdded   int64
	jobsProcess int64
}

func NewWorkerPool(workers int) *WorkerPool {
	ctx, cancel := context.WithCancel(context.Background())
	return &WorkerPool{
		jobs:    make(chan Job, workers*2),
		results: make(chan Result, workers*2),
		workers: workers,
		ctx:     ctx,
		cancel:  cancel,
		done:    make(chan struct{}),
	}
}

func (wp *WorkerPool) Start() {
	for i := 0; i < wp.workers; i++ {
		wp.wg.Add(1)
		go wp.worker(i)
	}
	
	go func() {
		wp.wg.Wait()
		close(wp.results)
		close(wp.done)
	}()
}

func (wp *WorkerPool) worker(id int) {
	defer wp.wg.Done()
	
	for {
		select {
		case job, ok := <-wp.jobs:
			if !ok {
				return
			}
			
			result := wp.processJob(job)
			atomic.AddInt64(&wp.jobsProcess, 1)
			
			select {
			case wp.results <- result:
			case <-wp.ctx.Done():
				return
			}
			
		case <-wp.ctx.Done():
			return
		}
	}
}

func (wp *WorkerPool) processJob(job Job) Result {
	// Simulate work
	time.Sleep(time.Duration(rand.Intn(100)) * time.Millisecond)
	
	// Simulate occasional errors
	if rand.Float32() < 0.1 {
		return Result{
			JobID: job.ID,
			Error: fmt.Errorf("job %d failed", job.ID),
		}
	}
	
	return Result{
		JobID: job.ID,
		Value: fmt.Sprintf("Processed job %d with data: %v", job.ID, job.Data),
	}
}

func (wp *WorkerPool) AddJob(job Job) {
	select {
	case wp.jobs <- job:
		atomic.AddInt64(&wp.jobsAdded, 1)
	case <-wp.ctx.Done():
		// Pool is shutting down
	}
}

func (wp *WorkerPool) GetResult() <-chan Result {
	return wp.results
}

func (wp *WorkerPool) Close() {
	close(wp.jobs)
}

func (wp *WorkerPool) Shutdown() {
	wp.cancel()
	<-wp.done
}

func (wp *WorkerPool) Stats() (int64, int64) {
	return atomic.LoadInt64(&wp.jobsAdded), atomic.LoadInt64(&wp.jobsProcess)
}

// Pipeline Pattern
type PipelineStage[T any] func(ctx context.Context, input <-chan T) <-chan T

type Pipeline[T any] struct {
	stages []PipelineStage[T]
}

func NewPipeline[T any]() *Pipeline[T] {
	return &Pipeline[T]{}
}

func (p *Pipeline[T]) AddStage(stage PipelineStage[T]) *Pipeline[T] {
	p.stages = append(p.stages, stage)
	return p
}

func (p *Pipeline[T]) Execute(ctx context.Context, input <-chan T) <-chan T {
	if len(p.stages) == 0 {
		return input
	}
	
	output := input
	for _, stage := range p.stages {
		output = stage(ctx, output)
	}
	
	return output
}

// Data processing stages
func FilterStage(predicate func(int) bool) PipelineStage[int] {
	return func(ctx context.Context, input <-chan int) <-chan int {
		output := make(chan int)
		
		go func() {
			defer close(output)
			for {
				select {
				case value, ok := <-input:
					if !ok {
						return
					}
					if predicate(value) {
						select {
						case output <- value:
						case <-ctx.Done():
							return
						}
					}
				case <-ctx.Done():
					return
				}
			}
		}()
		
		return output
	}
}

func TransformStage(transform func(int) int) PipelineStage[int] {
	return func(ctx context.Context, input <-chan int) <-chan int {
		output := make(chan int)
		
		go func() {
			defer close(output)
			for {
				select {
				case value, ok := <-input:
					if !ok {
						return
					}
					transformed := transform(value)
					select {
					case output <- transformed:
					case <-ctx.Done():
						return
					}
				case <-ctx.Done():
					return
				}
			}
		}()
		
		return output
	}
}

func BatchStage(batchSize int) PipelineStage[int] {
	return func(ctx context.Context, input <-chan int) <-chan int {
		output := make(chan int)
		
		go func() {
			defer close(output)
			batch := make([]int, 0, batchSize)
			
			for {
				select {
				case value, ok := <-input:
					if !ok {
						// Send remaining batch
						for _, v := range batch {
							select {
							case output <- v:
							case <-ctx.Done():
								return
							}
						}
						return
					}
					
					batch = append(batch, value)
					if len(batch) >= batchSize {
						// Process and send batch
						for _, v := range batch {
							select {
							case output <- v * 2: // Example batch processing
							case <-ctx.Done():
								return
							}
						}
						batch = batch[:0]
					}
					
				case <-ctx.Done():
					return
				}
			}
		}()
		
		return output
	}
}

// Fan-out/Fan-in Pattern
type FanOutFanIn struct {
	workers int
	bufSize int
}

func NewFanOutFanIn(workers, bufSize int) *FanOutFanIn {
	return &FanOutFanIn{
		workers: workers,
		bufSize: bufSize,
	}
}

func (f *FanOutFanIn) Process(ctx context.Context, input <-chan int, processor func(int) int) <-chan int {
	// Fan-out: distribute work to multiple workers
	workerInputs := make([]chan int, f.workers)
	for i := range workerInputs {
		workerInputs[i] = make(chan int, f.bufSize)
	}
	
	// Distribute input to workers in round-robin fashion
	go func() {
		defer func() {
			for _, ch := range workerInputs {
				close(ch)
			}
		}()
		
		workerIndex := 0
		for {
			select {
			case value, ok := <-input:
				if !ok {
					return
				}
				
				select {
				case workerInputs[workerIndex] <- value:
					workerIndex = (workerIndex + 1) % f.workers
				case <-ctx.Done():
					return
				}
				
			case <-ctx.Done():
				return
			}
		}
	}()
	
	// Fan-in: collect results from all workers
	output := make(chan int, f.bufSize)
	var wg sync.WaitGroup
	
	for i := 0; i < f.workers; i++ {
		wg.Add(1)
		go func(workerInput <-chan int) {
			defer wg.Done()
			
			for {
				select {
				case value, ok := <-workerInput:
					if !ok {
						return
					}
					
					result := processor(value)
					select {
					case output <- result:
					case <-ctx.Done():
						return
					}
					
				case <-ctx.Done():
					return
				}
			}
		}(workerInputs[i])
	}
	
	go func() {
		wg.Wait()
		close(output)
	}()
	
	return output
}

// Producer-Consumer Pattern with Rate Limiting
type RateLimitedProducer struct {
	rate     time.Duration
	burst    int
	output   chan interface{}
	limiter  *time.Ticker
	ctx      context.Context
	cancel   context.CancelFunc
	wg       sync.WaitGroup
}

func NewRateLimitedProducer(rate time.Duration, burst int) *RateLimitedProducer {
	ctx, cancel := context.WithCancel(context.Background())
	return &RateLimitedProducer{
		rate:    rate,
		burst:   burst,
		output:  make(chan interface{}, burst),
		limiter: time.NewTicker(rate),
		ctx:     ctx,
		cancel:  cancel,
	}
}

func (p *RateLimitedProducer) Start(producer func() interface{}) {
	p.wg.Add(1)
	go func() {
		defer p.wg.Done()
		defer close(p.output)
		defer p.limiter.Stop()
		
		for {
			select {
			case <-p.limiter.C:
				item := producer()
				if item == nil {
					return // Signal to stop production
				}
				
				select {
				case p.output <- item:
				case <-p.ctx.Done():
					return
				}
				
			case <-p.ctx.Done():
				return
			}
		}
	}()
}

func (p *RateLimitedProducer) Output() <-chan interface{} {
	return p.output
}

func (p *RateLimitedProducer) Stop() {
	p.cancel()
	p.wg.Wait()
}

// Concurrent Map with Sync.Map alternative
type SafeMap[K comparable, V any] struct {
	mu   sync.RWMutex
	data map[K]V
}

func NewSafeMap[K comparable, V any]() *SafeMap[K, V] {
	return &SafeMap[K, V]{
		data: make(map[K]V),
	}
}

func (sm *SafeMap[K, V]) Set(key K, value V) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.data[key] = value
}

func (sm *SafeMap[K, V]) Get(key K) (V, bool) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	value, exists := sm.data[key]
	return value, exists
}

func (sm *SafeMap[K, V]) Delete(key K) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	delete(sm.data, key)
}

func (sm *SafeMap[K, V]) Range(fn func(K, V) bool) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	
	for k, v := range sm.data {
		if !fn(k, v) {
			break
		}
	}
}

func (sm *SafeMap[K, V]) Len() int {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	return len(sm.data)
}

// Semaphore Pattern
type Semaphore struct {
	ch chan struct{}
}

func NewSemaphore(capacity int) *Semaphore {
	return &Semaphore{
		ch: make(chan struct{}, capacity),
	}
}

func (s *Semaphore) Acquire(ctx context.Context) error {
	select {
	case s.ch <- struct{}{}:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *Semaphore) Release() {
	<-s.ch
}

// Timeout Pattern with Context
func WithTimeout[T any](ctx context.Context, timeout time.Duration, fn func(context.Context) (T, error)) (T, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	
	type result struct {
		value T
		err   error
	}
	
	resultCh := make(chan result, 1)
	
	go func() {
		value, err := fn(ctx)
		resultCh <- result{value: value, err: err}
	}()
	
	select {
	case res := <-resultCh:
		return res.value, res.err
	case <-ctx.Done():
		var zero T
		return zero, ctx.Err()
	}
}

// Publish-Subscribe Pattern
type Event struct {
	Type string
	Data interface{}
}

type EventBus struct {
	subscribers map[string][]chan Event
	mu          sync.RWMutex
	bufferSize  int
}

func NewEventBus(bufferSize int) *EventBus {
	return &EventBus{
		subscribers: make(map[string][]chan Event),
		bufferSize:  bufferSize,
	}
}

func (eb *EventBus) Subscribe(eventType string) <-chan Event {
	eb.mu.Lock()
	defer eb.mu.Unlock()
	
	ch := make(chan Event, eb.bufferSize)
	eb.subscribers[eventType] = append(eb.subscribers[eventType], ch)
	
	return ch
}

func (eb *EventBus) Publish(event Event) {
	eb.mu.RLock()
	defer eb.mu.RUnlock()
	
	subscribers, exists := eb.subscribers[event.Type]
	if !exists {
		return
	}
	
	for _, ch := range subscribers {
		select {
		case ch <- event:
		default:
			// Channel is full, skip this subscriber
		}
	}
}

func (eb *EventBus) Unsubscribe(eventType string, ch <-chan Event) {
	eb.mu.Lock()
	defer eb.mu.Unlock()
	
	subscribers := eb.subscribers[eventType]
	for i, subscriber := range subscribers {
		if subscriber == ch {
			// Remove this subscriber
			eb.subscribers[eventType] = append(subscribers[:i], subscribers[i+1:]...)
			close(subscriber)
			break
		}
	}
}

// Circuit Breaker Pattern
type CircuitState int

const (
	Closed CircuitState = iota
	Open
	HalfOpen
)

type CircuitBreaker struct {
	mu                sync.RWMutex
	state             CircuitState
	failureCount      int
	successCount      int
	lastFailure       time.Time
	failureThreshold  int
	successThreshold  int
	timeout           time.Duration
}

func NewCircuitBreaker(failureThreshold, successThreshold int, timeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:            Closed,
		failureThreshold: failureThreshold,
		successThreshold: successThreshold,
		timeout:          timeout,
	}
}

func (cb *CircuitBreaker) Execute(fn func() error) error {
	if !cb.canExecute() {
		return fmt.Errorf("circuit breaker is open")
	}
	
	err := fn()
	
	if err != nil {
		cb.onFailure()
		return err
	}
	
	cb.onSuccess()
	return nil
}

func (cb *CircuitBreaker) canExecute() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	
	switch cb.state {
	case Closed:
		return true
	case Open:
		return time.Since(cb.lastFailure) > cb.timeout
	case HalfOpen:
		return true
	}
	
	return false
}

func (cb *CircuitBreaker) onSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	
	switch cb.state {
	case Closed:
		cb.failureCount = 0
	case HalfOpen:
		cb.successCount++
		if cb.successCount >= cb.successThreshold {
			cb.state = Closed
			cb.failureCount = 0
			cb.successCount = 0
		}
	}
}

func (cb *CircuitBreaker) onFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	
	cb.lastFailure = time.Now()
	
	switch cb.state {
	case Closed:
		cb.failureCount++
		if cb.failureCount >= cb.failureThreshold {
			cb.state = Open
		}
	case HalfOpen:
		cb.state = Open
		cb.successCount = 0
	}
}

func (cb *CircuitBreaker) State() CircuitState {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	return cb.state
}

// Retry Pattern with Exponential Backoff
type RetryConfig struct {
	MaxRetries    int
	BaseDelay     time.Duration
	MaxDelay      time.Duration
	BackoffFactor float64
}

func RetryWithBackoff[T any](ctx context.Context, config RetryConfig, fn func() (T, error)) (T, error) {
	var lastErr error
	delay := config.BaseDelay
	
	for attempt := 0; attempt <= config.MaxRetries; attempt++ {
		if attempt > 0 {
			select {
			case <-time.After(delay):
			case <-ctx.Done():
				var zero T
				return zero, ctx.Err()
			}
			
			// Calculate next delay with exponential backoff
			delay = time.Duration(float64(delay) * config.BackoffFactor)
			if delay > config.MaxDelay {
				delay = config.MaxDelay
			}
		}
		
		result, err := fn()
		if err == nil {
			return result, nil
		}
		
		lastErr = err
		
		// Don't retry on context cancellation
		select {
		case <-ctx.Done():
			return result, ctx.Err()
		default:
		}
	}
	
	var zero T
	return zero, fmt.Errorf("max retries exceeded, last error: %w", lastErr)
}

// Main function demonstrating all patterns
func main() {
	fmt.Println("Concurrency Patterns Demo")
	
	// Worker Pool Example
	fmt.Println("\n=== Worker Pool Pattern ===")
	pool := NewWorkerPool(4)
	pool.Start()
	
	// Add jobs
	for i := 0; i < 20; i++ {
		pool.AddJob(Job{
			ID:   i,
			Data: fmt.Sprintf("data-%d", i),
		})
	}
	
	pool.Close()
	
	// Collect results
	go func() {
		for result := range pool.GetResult() {
			if result.Error != nil {
				fmt.Printf("Job %d failed: %v\n", result.JobID, result.Error)
			} else {
				fmt.Printf("Job %d result: %v\n", result.JobID, result.Value)
			}
		}
	}()
	
	time.Sleep(2 * time.Second)
	added, processed := pool.Stats()
	fmt.Printf("Jobs added: %d, processed: %d\n", added, processed)
	pool.Shutdown()
	
	// Pipeline Example
	fmt.Println("\n=== Pipeline Pattern ===")
	ctx := context.Background()
	
	input := make(chan int, 10)
	go func() {
		defer close(input)
		for i := 1; i <= 10; i++ {
			input <- i
		}
	}()
	
	pipeline := NewPipeline[int]().
		AddStage(FilterStage(func(x int) bool { return x%2 == 0 })).
		AddStage(TransformStage(func(x int) int { return x * x })).
		AddStage(BatchStage(2))
	
	output := pipeline.Execute(ctx, input)
	
	for result := range output {
		fmt.Printf("Pipeline result: %d\n", result)
	}
	
	// Fan-out/Fan-in Example
	fmt.Println("\n=== Fan-out/Fan-in Pattern ===")
	fanoutInput := make(chan int, 10)
	go func() {
		defer close(fanoutInput)
		for i := 1; i <= 20; i++ {
			fanoutInput <- i
		}
	}()
	
	fanout := NewFanOutFanIn(4, 5)
	fanoutOutput := fanout.Process(ctx, fanoutInput, func(x int) int {
		time.Sleep(100 * time.Millisecond) // Simulate work
		return x * x
	})
	
	for result := range fanoutOutput {
		fmt.Printf("Fan-out/Fan-in result: %d\n", result)
	}
	
	// Rate Limited Producer Example
	fmt.Println("\n=== Rate Limited Producer Pattern ===")
	producer := NewRateLimitedProducer(500*time.Millisecond, 5)
	counter := 0
	
	producer.Start(func() interface{} {
		counter++
		if counter > 5 {
			return nil // Stop production
		}
		return fmt.Sprintf("Item %d", counter)
	})
	
	for item := range producer.Output() {
		fmt.Printf("Produced: %v\n", item)
	}
	
	producer.Stop()
	
	// Event Bus Example
	fmt.Println("\n=== Event Bus Pattern ===")
	eventBus := NewEventBus(10)
	
	subscriber1 := eventBus.Subscribe("user.created")
	subscriber2 := eventBus.Subscribe("user.updated")
	
	go func() {
		for event := range subscriber1 {
			fmt.Printf("Subscriber 1 received: %s - %v\n", event.Type, event.Data)
		}
	}()
	
	go func() {
		for event := range subscriber2 {
			fmt.Printf("Subscriber 2 received: %s - %v\n", event.Type, event.Data)
		}
	}()
	
	// Publish events
	eventBus.Publish(Event{Type: "user.created", Data: "User John Doe created"})
	eventBus.Publish(Event{Type: "user.updated", Data: "User John Doe updated"})
	
	time.Sleep(100 * time.Millisecond)
	
	// Circuit Breaker Example
	fmt.Println("\n=== Circuit Breaker Pattern ===")
	cb := NewCircuitBreaker(3, 2, 2*time.Second)
	
	// Simulate failing operation
	failingOperation := func() error {
		if rand.Float32() < 0.7 { // 70% chance of failure
			return fmt.Errorf("operation failed")
		}
		return nil
	}
	
	for i := 0; i < 10; i++ {
		err := cb.Execute(failingOperation)
		fmt.Printf("Attempt %d: State=%d, Error=%v\n", i+1, cb.State(), err)
		time.Sleep(500 * time.Millisecond)
	}
	
	// Retry with Backoff Example
	fmt.Println("\n=== Retry with Backoff Pattern ===")
	retryConfig := RetryConfig{
		MaxRetries:    3,
		BaseDelay:     100 * time.Millisecond,
		MaxDelay:      1 * time.Second,
		BackoffFactor: 2.0,
	}
	
	unstableOperation := func() (string, error) {
		if rand.Float32() < 0.6 { // 60% chance of failure
			return "", fmt.Errorf("temporary failure")
		}
		return "success", nil
	}
	
	result, err := RetryWithBackoff(ctx, retryConfig, unstableOperation)
	fmt.Printf("Retry result: %s, error: %v\n", result, err)
	
	// Semaphore Example
	fmt.Println("\n=== Semaphore Pattern ===")
	sem := NewSemaphore(3) // Only allow 3 concurrent operations
	var wg sync.WaitGroup
	
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			
			if err := sem.Acquire(ctx); err != nil {
				fmt.Printf("Worker %d failed to acquire semaphore: %v\n", id, err)
				return
			}
			defer sem.Release()
			
			fmt.Printf("Worker %d is working...\n", id)
			time.Sleep(1 * time.Second)
			fmt.Printf("Worker %d is done\n", id)
		}(i)
	}
	
	wg.Wait()
	
	// Safe Map Example
	fmt.Println("\n=== Safe Map Pattern ===")
	safeMap := NewSafeMap[string, int]()
	
	var mapWG sync.WaitGroup
	
	// Writers
	for i := 0; i < 5; i++ {
		mapWG.Add(1)
		go func(id int) {
			defer mapWG.Done()
			for j := 0; j < 10; j++ {
				key := fmt.Sprintf("key-%d-%d", id, j)
				safeMap.Set(key, id*10+j)
			}
		}(i)
	}
	
	// Readers
	for i := 0; i < 3; i++ {
		mapWG.Add(1)
		go func(id int) {
			defer mapWG.Done()
			time.Sleep(100 * time.Millisecond)
			
			count := 0
			safeMap.Range(func(k string, v int) bool {
				count++
				return true
			})
			fmt.Printf("Reader %d: map has %d items\n", id, count)
		}(i)
	}
	
	mapWG.Wait()
	fmt.Printf("Final map size: %d\n", safeMap.Len())
	
	fmt.Printf("\nRuntime info: GOMAXPROCS=%d, NumGoroutine=%d\n", 
		runtime.GOMAXPROCS(0), runtime.NumGoroutine())
}
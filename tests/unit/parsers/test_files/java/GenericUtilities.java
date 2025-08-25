package com.example.utils;

import java.util.*;
import java.util.function.*;
import java.util.stream.Collectors;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

/**
 * Advanced generic utilities demonstrating complex Java generics,
 * lambda expressions, method references, and modern Java features.
 * 
 * @param <T> The base type for utility operations
 */
public class GenericUtilities<T extends Comparable<T> & Serializable> {

    private final Class<T> typeClass;
    private final Map<String, T> cache = new ConcurrentHashMap<>();
    
    // Complex constructor with reflection
    @SuppressWarnings("unchecked")
    public GenericUtilities() {
        Type superClass = getClass().getGenericSuperclass();
        if (superClass instanceof ParameterizedType) {
            this.typeClass = (Class<T>) ((ParameterizedType) superClass).getActualTypeArguments()[0];
        } else {
            throw new IllegalStateException("Cannot determine type parameter");
        }
    }

    /**
     * Complex generic method with multiple bounds and wildcards
     */
    public <U extends T, V extends Collection<? super U>> 
    CompletableFuture<Optional<U>> processCollectionAsync(
            V collection,
            Predicate<? super U> filter,
            Function<? super U, ? extends U> transformer) {
        
        return CompletableFuture.supplyAsync(() -> {
            return collection.stream()
                    .filter(item -> item instanceof T)
                    .map(item -> (U) item)
                    .filter(filter)
                    .map(transformer)
                    .findFirst();
        });
    }

    /**
     * Method with complex generic return type and exception handling
     */
    public <K, V, E extends Exception> 
    Map<K, List<V>> groupAndTransform(
            Collection<T> items,
            Function<T, K> keyExtractor,
            Function<T, V> valueTransformer,
            Supplier<E> exceptionSupplier) throws E {
        
        if (items == null || items.isEmpty()) {
            throw exceptionSupplier.get();
        }

        return items.stream()
                .collect(Collectors.groupingBy(
                    keyExtractor,
                    Collectors.mapping(
                        valueTransformer,
                        Collectors.toList()
                    )
                ));
    }

    /**
     * Builder pattern with fluent interface and method chaining
     */
    public static class FluentBuilder<T extends Comparable<T>> {
        private List<T> items = new ArrayList<>();
        private Comparator<T> comparator = T::compareTo;
        private Predicate<T> filter = item -> true;

        private FluentBuilder() {}

        public static <T extends Comparable<T>> FluentBuilder<T> create() {
            return new FluentBuilder<T>();
        }

        public FluentBuilder<T> addItem(T item) {
            this.items.add(item);
            return this;
        }

        public FluentBuilder<T> addAll(Collection<? extends T> items) {
            this.items.addAll(items);
            return this;
        }

        public FluentBuilder<T> sortBy(Comparator<T> comparator) {
            this.comparator = comparator;
            return this;
        }

        public FluentBuilder<T> filterBy(Predicate<T> filter) {
            this.filter = this.filter.and(filter);
            return this;
        }

        public List<T> build() {
            return items.stream()
                    .filter(filter)
                    .sorted(comparator)
                    .collect(Collectors.toList());
        }

        public Optional<T> buildFirst() {
            return items.stream()
                    .filter(filter)
                    .sorted(comparator)
                    .findFirst();
        }
    }

    /**
     * Complex nested generic class with multiple type parameters
     */
    public static class NestedProcessor<T, U extends Collection<T>, V extends Map<String, T>> {
        
        private final Function<T, String> keyGenerator;
        private final Supplier<U> collectionFactory;
        private final Supplier<V> mapFactory;

        public NestedProcessor(
                Function<T, String> keyGenerator,
                Supplier<U> collectionFactory,
                Supplier<V> mapFactory) {
            this.keyGenerator = keyGenerator;
            this.collectionFactory = collectionFactory;
            this.mapFactory = mapFactory;
        }

        public V process(Stream<T> stream) {
            V result = mapFactory.get();
            stream.forEach(item -> result.put(keyGenerator.apply(item), item));
            return result;
        }

        /**
         * Inner class with its own generic parameters
         */
        public class ProcessorCallback<R> implements Function<T, R> {
            private final Function<T, R> transformer;
            private final Consumer<R> resultHandler;

            public ProcessorCallback(Function<T, R> transformer, Consumer<R> resultHandler) {
                this.transformer = transformer;
                this.resultHandler = resultHandler;
            }

            @Override
            public R apply(T input) {
                R result = transformer.apply(input);
                resultHandler.accept(result);
                return result;
            }

            /**
             * Method with bounded wildcard and intersection types
             */
            public <S extends Comparable<S> & Serializable> 
            List<S> processComparableItems(Collection<? extends S> items) {
                return items.stream()
                        .sorted()
                        .collect(Collectors.toList());
            }
        }
    }

    /**
     * Abstract inner class demonstrating complex inheritance hierarchy
     */
    public abstract static class AbstractDataProcessor<T> {
        
        protected final String processorName;
        protected final Map<String, Object> configuration;

        protected AbstractDataProcessor(String processorName) {
            this.processorName = processorName;
            this.configuration = new HashMap<>();
        }

        // Abstract method to be implemented by subclasses
        public abstract ProcessingResult<T> process(T data);

        // Template method pattern
        public final ProcessingResult<T> safeProcess(T data) {
            try {
                validateData(data);
                ProcessingResult<T> result = process(data);
                postProcess(result);
                return result;
            } catch (Exception e) {
                return ProcessingResult.failure(e.getMessage());
            }
        }

        protected void validateData(T data) throws ValidationException {
            if (data == null) {
                throw new ValidationException("Data cannot be null");
            }
        }

        protected void postProcess(ProcessingResult<T> result) {
            // Default post-processing - can be overridden
        }

        // Static factory method
        public static <T> AbstractDataProcessor<T> createDefault(String name) {
            return new DefaultDataProcessor<>(name);
        }

        /**
         * Default implementation as private static nested class
         */
        private static class DefaultDataProcessor<T> extends AbstractDataProcessor<T> {
            
            private DefaultDataProcessor(String processorName) {
                super(processorName);
            }

            @Override
            public ProcessingResult<T> process(T data) {
                // Simple pass-through processing
                return ProcessingResult.success(data);
            }
        }
    }

    /**
     * Generic functional interface with multiple type parameters
     */
    @FunctionalInterface
    public interface TriFunction<T, U, V, R> {
        R apply(T t, U u, V v);

        // Default method with complex generic signature
        default <W> TriFunction<T, U, V, W> andThen(Function<? super R, ? extends W> after) {
            Objects.requireNonNull(after);
            return (T t, U u, V v) -> after.apply(apply(t, u, v));
        }

        // Static method with bounded wildcards
        static <T extends Comparable<T>, U extends Collection<T>, V extends Map<String, T>, R>
        TriFunction<T, U, V, R> of(TriFunction<T, U, V, R> function) {
            return function;
        }
    }

    /**
     * Enum with complex methods and generic capabilities
     */
    public enum ProcessingMode {
        SEQUENTIAL("Sequential Processing") {
            @Override
            public <T> Stream<T> createStream(Collection<T> collection) {
                return collection.stream();
            }
        },
        PARALLEL("Parallel Processing") {
            @Override
            public <T> Stream<T> createStream(Collection<T> collection) {
                return collection.parallelStream();
            }
        };

        private final String description;

        ProcessingMode(String description) {
            this.description = description;
        }

        public String getDescription() {
            return description;
        }

        // Abstract method in enum
        public abstract <T> Stream<T> createStream(Collection<T> collection);

        // Static method with generics in enum
        public static <T extends Enum<T> & ProcessingMode> T getByDescription(String description) {
            for (ProcessingMode mode : values()) {
                if (mode.description.equals(description)) {
                    return (T) mode;
                }
            }
            throw new IllegalArgumentException("No mode found with description: " + description);
        }
    }

    /**
     * Record with generic parameters (Java 14+)
     */
    public record ProcessingResult<T>(
        boolean success,
        T data,
        String message,
        Optional<Exception> error
    ) {
        // Compact constructor with validation
        public ProcessingResult {
            message = message != null ? message : "";
        }

        // Static factory methods
        public static <T> ProcessingResult<T> success(T data) {
            return new ProcessingResult<>(true, data, "Success", Optional.empty());
        }

        public static <T> ProcessingResult<T> failure(String message) {
            return new ProcessingResult<>(false, null, message, Optional.empty());
        }

        public static <T> ProcessingResult<T> failure(Exception error) {
            return new ProcessingResult<>(false, null, error.getMessage(), Optional.of(error));
        }

        // Instance method with generics
        public <U> ProcessingResult<U> map(Function<T, U> mapper) {
            if (success && data != null) {
                return ProcessingResult.success(mapper.apply(data));
            }
            return ProcessingResult.failure(message);
        }
    }

    /**
     * Custom annotation with complex parameters
     */
    @Target({ElementType.METHOD, ElementType.TYPE, ElementType.FIELD})
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ProcessorConfig {
        String name() default "";
        Class<?>[] supportedTypes() default {};
        ProcessingMode mode() default ProcessingMode.SEQUENTIAL;
        String[] tags() default {};
        boolean cacheable() default true;
    }

    /**
     * Method demonstrating annotation usage and complex generics
     */
    @ProcessorConfig(
        name = "complexTransformer",
        supportedTypes = {String.class, Integer.class, List.class},
        mode = ProcessingMode.PARALLEL,
        tags = {"transformer", "async", "cached"}
    )
    public <U extends T, V extends Collection<U>> 
    CompletableFuture<ProcessingResult<V>> transformAsync(
            V input,
            Function<U, U> transformer,
            Predicate<U> validator) {
        
        return CompletableFuture.supplyAsync(() -> {
            try {
                V result = (V) input.stream()
                    .map(transformer)
                    .filter(validator)
                    .collect(Collectors.toCollection(
                        () -> createCollectionOfType((Class<V>) input.getClass())
                    ));
                
                return ProcessingResult.success(result);
            } catch (Exception e) {
                return ProcessingResult.failure(e);
            }
        });
    }

    // Complex reflection-based method
    @SuppressWarnings("unchecked")
    private <V extends Collection<T>> V createCollectionOfType(Class<V> collectionClass) {
        if (List.class.isAssignableFrom(collectionClass)) {
            return (V) new ArrayList<T>();
        } else if (Set.class.isAssignableFrom(collectionClass)) {
            return (V) new HashSet<T>();
        } else if (Queue.class.isAssignableFrom(collectionClass)) {
            return (V) new LinkedList<T>();
        } else {
            throw new IllegalArgumentException("Unsupported collection type: " + collectionClass);
        }
    }

    // Custom exception with generic information
    public static class ValidationException extends Exception {
        private final Object invalidData;
        private final Class<?> expectedType;

        public <T> ValidationException(String message, T invalidData, Class<T> expectedType) {
            super(message);
            this.invalidData = invalidData;
            this.expectedType = expectedType;
        }

        public Object getInvalidData() {
            return invalidData;
        }

        public Class<?> getExpectedType() {
            return expectedType;
        }
    }
}
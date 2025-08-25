// Advanced TypeScript features demonstrating complex type system capabilities
import { Observable, Subject, BehaviorSubject, combineLatest } from 'rxjs';
import { map, filter, debounceTime, distinctUntilChanged, switchMap } from 'rxjs/operators';

// Complex generic type definitions with constraints
type Prettify<T> = {
    [K in keyof T]: T[K];
} & {};

type DeepPartial<T> = {
    [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

type RequireAtLeastOne<T, Keys extends keyof T = keyof T> =
    Pick<T, Exclude<keyof T, Keys>> &
    {
        [K in Keys]-?: Required<Pick<T, K>> & Partial<Pick<T, Keys>>
    }[Keys];

// Conditional types with complex logic
type IsArray<T> = T extends readonly unknown[] ? true : false;
type ArrayElement<T> = T extends readonly (infer U)[] ? U : never;
type NonNullable<T> = T extends null | undefined ? never : T;

// Template literal types and mapped types
type EventName<T extends string> = `on${Capitalize<T>}`;
type HandlerName<T extends string> = `handle${Capitalize<T>}`;

type ApiRoutes = 'users' | 'orders' | 'products' | 'analytics';
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
type ApiEndpoint<Route extends ApiRoutes, Method extends HttpMethod> = 
    `${Method} /${Route}`;

// Complex interface with generic constraints
interface Repository<T, K extends keyof T = keyof T> {
    findById(id: T[K]): Promise<T | null>;
    findMany(criteria: Partial<T>): Promise<T[]>;
    create(entity: Omit<T, K>): Promise<T>;
    update(id: T[K], updates: Partial<T>): Promise<T>;
    delete(id: T[K]): Promise<boolean>;
    query<R>(selector: (entity: T) => R): Promise<R[]>;
}

// Advanced utility types
type PickByType<T, U> = {
    [K in keyof T as T[K] extends U ? K : never]: T[K];
};

type OmitByType<T, U> = {
    [K in keyof T as T[K] extends U ? never : K]: T[K];
};

type FunctionPropertyNames<T> = {
    [K in keyof T]: T[K] extends Function ? K : never;
}[keyof T];

type NonFunctionPropertyNames<T> = {
    [K in keyof T]: T[K] extends Function ? never : K;
}[keyof T];

// Complex namespace with nested types and functions
namespace DataProcessing {
    export interface ProcessorConfig<T> {
        batchSize: number;
        timeout: number;
        retryAttempts: number;
        validator?: (item: T) => boolean;
        transformer?: (item: T) => T;
        errorHandler?: (error: Error, item: T) => void;
    }

    export interface ProcessingResult<T, E = Error> {
        successful: T[];
        failed: Array<{ item: T; error: E }>;
        metrics: ProcessingMetrics;
    }

    export interface ProcessingMetrics {
        totalItems: number;
        processedItems: number;
        failedItems: number;
        processingTimeMs: number;
        throughputPerSecond: number;
    }

    export abstract class BaseProcessor<T, R = T> {
        protected abstract process(item: T): Promise<R> | R;
        
        public async processMany(
            items: T[],
            config: ProcessorConfig<T> = this.defaultConfig
        ): Promise<ProcessingResult<R>> {
            const startTime = Date.now();
            const successful: R[] = [];
            const failed: Array<{ item: T; error: Error }> = [];

            for (const item of items) {
                try {
                    if (config.validator && !config.validator(item)) {
                        continue;
                    }

                    const processedItem = config.transformer ? config.transformer(item) : item;
                    const result = await this.process(processedItem);
                    successful.push(result);
                } catch (error) {
                    const errorObj = error instanceof Error ? error : new Error(String(error));
                    failed.push({ item, error: errorObj });
                    
                    if (config.errorHandler) {
                        config.errorHandler(errorObj, item);
                    }
                }
            }

            const endTime = Date.now();
            const processingTimeMs = endTime - startTime;

            return {
                successful,
                failed,
                metrics: {
                    totalItems: items.length,
                    processedItems: successful.length,
                    failedItems: failed.length,
                    processingTimeMs,
                    throughputPerSecond: successful.length / (processingTimeMs / 1000)
                }
            };
        }

        protected get defaultConfig(): ProcessorConfig<T> {
            return {
                batchSize: 100,
                timeout: 30000,
                retryAttempts: 3
            };
        }
    }

    export class JsonProcessor extends BaseProcessor<unknown, object> {
        protected process(item: unknown): object {
            if (typeof item === 'string') {
                try {
                    return JSON.parse(item);
                } catch {
                    throw new Error(`Invalid JSON: ${item}`);
                }
            } else if (typeof item === 'object' && item !== null) {
                return item as object;
            } else {
                throw new Error(`Cannot process item of type: ${typeof item}`);
            }
        }
    }
}

// Complex class with multiple generic parameters and constraints
class StateManager<
    TState extends Record<string, unknown>,
    TAction extends { type: string; payload?: unknown },
    TSelector extends (state: TState) => unknown = (state: TState) => TState
> {
    private state$ = new BehaviorSubject<TState>(this.initialState);
    private actions$ = new Subject<TAction>();

    constructor(
        private initialState: TState,
        private reducer: (state: TState, action: TAction) => TState
    ) {
        // Set up action processing pipeline
        this.actions$.pipe(
            debounceTime(10), // Batch rapid actions
            map(action => this.reducer(this.state$.value, action))
        ).subscribe(newState => {
            this.state$.next(newState);
        });
    }

    // Generic dispatch method with action type inference
    dispatch<T extends TAction>(action: T): void {
        this.actions$.next(action);
    }

    // Complex selector method with conditional types
    select<R>(selector: TSelector): Observable<R> {
        return this.state$.pipe(
            map(selector as (state: TState) => R),
            distinctUntilChanged()
        );
    }

    // Method with complex return type inference
    selectMultiple<Selectors extends Record<string, (state: TState) => unknown>>(
        selectors: Selectors
    ): Observable<{
        [K in keyof Selectors]: Selectors[K] extends (state: TState) => infer R ? R : never;
    }> {
        const observables = Object.entries(selectors).map(([key, selector]) =>
            this.state$.pipe(
                map(selector),
                distinctUntilChanged(),
                map(value => ({ [key]: value }))
            )
        );

        return combineLatest(observables).pipe(
            map(results => results.reduce((acc, curr) => ({ ...acc, ...curr }), {} as any))
        );
    }

    // Complex method with conditional return types
    async executeTransaction<T>(
        transaction: (currentState: TState) => Promise<T> | T,
        rollbackOnError = true
    ): Promise<T | null> {
        const originalState = this.state$.value;
        
        try {
            const result = await transaction(originalState);
            return result;
        } catch (error) {
            if (rollbackOnError) {
                this.state$.next(originalState);
            }
            console.error('Transaction failed:', error);
            return null;
        }
    }

    // Method demonstrating function overloading in TypeScript
    snapshot(): TState;
    snapshot<K extends keyof TState>(key: K): TState[K];
    snapshot<K extends keyof TState>(key?: K): TState | TState[K] {
        const currentState = this.state$.value;
        return key !== undefined ? currentState[key] : currentState;
    }

    dispose(): void {
        this.state$.complete();
        this.actions$.complete();
    }
}

// Complex interface with mapped types and conditional properties
interface ApiResponse<T> {
    data: T;
    status: 'success' | 'error' | 'pending';
    message?: string;
    errors?: ValidationError[];
    pagination?: {
        page: number;
        limit: number;
        total: number;
        hasNext: boolean;
        hasPrevious: boolean;
    };
}

interface ValidationError {
    field: string;
    message: string;
    code: string;
}

// Generic API client with complex method signatures
class ApiClient {
    constructor(private baseUrl: string, private defaultHeaders: Record<string, string> = {}) {}

    // Method with complex generic constraints and conditional types
    async request<
        TResponse,
        TPayload = never,
        TParams = Record<string, string | number | boolean>
    >(
        method: HttpMethod,
        endpoint: string,
        options: {
            payload?: TPayload;
            params?: TParams;
            headers?: Record<string, string>;
        } = {}
    ): Promise<ApiResponse<TResponse>> {
        const url = new URL(endpoint, this.baseUrl);
        
        // Add query parameters
        if (options.params) {
            Object.entries(options.params).forEach(([key, value]) => {
                url.searchParams.append(key, String(value));
            });
        }

        const response = await fetch(url.toString(), {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...this.defaultHeaders,
                ...options.headers
            },
            body: options.payload ? JSON.stringify(options.payload) : undefined
        });

        const responseData = await response.json() as ApiResponse<TResponse>;
        
        if (!response.ok) {
            throw new ApiError(response.status, responseData.message || 'Request failed', responseData.errors);
        }

        return responseData;
    }

    // Specialized methods with type-safe endpoints
    async get<T>(endpoint: string, params?: Record<string, unknown>): Promise<ApiResponse<T>> {
        return this.request<T>('GET', endpoint, { params });
    }

    async post<T, P>(endpoint: string, payload: P): Promise<ApiResponse<T>> {
        return this.request<T, P>('POST', endpoint, { payload });
    }

    async put<T, P>(endpoint: string, payload: P): Promise<ApiResponse<T>> {
        return this.request<T, P>('PUT', endpoint, { payload });
    }

    async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
        return this.request<T>('DELETE', endpoint);
    }

    // Generic method with builder pattern
    builder() {
        return new RequestBuilder(this);
    }
}

// Builder pattern with fluent interface and type safety
class RequestBuilder {
    private _method: HttpMethod = 'GET';
    private _endpoint = '';
    private _payload?: unknown;
    private _params?: Record<string, unknown>;
    private _headers?: Record<string, string>;

    constructor(private client: ApiClient) {}

    method(method: HttpMethod): this {
        this._method = method;
        return this;
    }

    endpoint(endpoint: string): this {
        this._endpoint = endpoint;
        return this;
    }

    payload<T>(payload: T): this {
        this._payload = payload;
        return this;
    }

    params(params: Record<string, unknown>): this {
        this._params = { ...this._params, ...params };
        return this;
    }

    headers(headers: Record<string, string>): this {
        this._headers = { ...this._headers, ...headers };
        return this;
    }

    async execute<T>(): Promise<ApiResponse<T>> {
        return this.client.request<T>(this._method, this._endpoint, {
            payload: this._payload,
            params: this._params,
            headers: this._headers
        });
    }
}

// Custom error class with detailed information
class ApiError extends Error {
    constructor(
        public status: number,
        message: string,
        public errors?: ValidationError[]
    ) {
        super(message);
        this.name = 'ApiError';
    }

    get isClientError(): boolean {
        return this.status >= 400 && this.status < 500;
    }

    get isServerError(): boolean {
        return this.status >= 500;
    }

    getErrorsForField(field: string): ValidationError[] {
        return this.errors?.filter(error => error.field === field) || [];
    }
}

// Complex decorator implementations
function memoize<T extends (...args: any[]) => any>(
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor
): PropertyDescriptor {
    const originalMethod = descriptor.value as T;
    const cache = new Map<string, ReturnType<T>>();

    descriptor.value = function(...args: Parameters<T>): ReturnType<T> {
        const key = JSON.stringify(args);
        
        if (cache.has(key)) {
            return cache.get(key)!;
        }

        const result = originalMethod.apply(this, args);
        cache.set(key, result);
        return result;
    };

    return descriptor;
}

function retry<T extends (...args: any[]) => Promise<any>>(attempts: number = 3) {
    return function(
        target: any,
        propertyKey: string,
        descriptor: PropertyDescriptor
    ): PropertyDescriptor {
        const originalMethod = descriptor.value as T;

        descriptor.value = async function(...args: Parameters<T>): Promise<ReturnType<T>> {
            let lastError: Error;
            
            for (let i = 0; i < attempts; i++) {
                try {
                    return await originalMethod.apply(this, args);
                } catch (error) {
                    lastError = error instanceof Error ? error : new Error(String(error));
                    
                    if (i === attempts - 1) {
                        throw lastError;
                    }
                    
                    // Exponential backoff
                    await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
                }
            }
            
            throw lastError!;
        };

        return descriptor;
    };
}

// Complex service class demonstrating multiple TypeScript features
abstract class BaseService<TModel, TCreateDto, TUpdateDto, TId = string> {
    constructor(
        protected repository: Repository<TModel, keyof TModel>,
        protected apiClient: ApiClient
    ) {}

    abstract validateCreate(dto: TCreateDto): Promise<ValidationError[]>;
    abstract validateUpdate(dto: TUpdateDto): Promise<ValidationError[]>;
    abstract mapToModel(dto: TCreateDto | TUpdateDto): Partial<TModel>;

    @memoize
    async findById(id: TId): Promise<TModel | null> {
        try {
            return await this.repository.findById(id as any);
        } catch (error) {
            console.error('Error finding entity by ID:', error);
            return null;
        }
    }

    @retry(3)
    async create(dto: TCreateDto): Promise<TModel> {
        const validationErrors = await this.validateCreate(dto);
        
        if (validationErrors.length > 0) {
            throw new ValidationException('Validation failed', validationErrors);
        }

        const modelData = this.mapToModel(dto);
        return await this.repository.create(modelData as any);
    }

    async update(id: TId, dto: TUpdateDto): Promise<TModel> {
        const validationErrors = await this.validateUpdate(dto);
        
        if (validationErrors.length > 0) {
            throw new ValidationException('Validation failed', validationErrors);
        }

        const updateData = this.mapToModel(dto);
        return await this.repository.update(id as any, updateData);
    }

    // Complex generic method with multiple type constraints
    async bulkProcess<TResult>(
        items: TModel[],
        processor: (item: TModel) => Promise<TResult> | TResult,
        options: {
            concurrency?: number;
            failFast?: boolean;
            progressCallback?: (completed: number, total: number) => void;
        } = {}
    ): Promise<Array<{ item: TModel; result?: TResult; error?: Error }>> {
        const { concurrency = 5, failFast = false, progressCallback } = options;
        const results: Array<{ item: TModel; result?: TResult; error?: Error }> = [];
        
        // Process items in batches
        for (let i = 0; i < items.length; i += concurrency) {
            const batch = items.slice(i, i + concurrency);
            
            const batchPromises = batch.map(async (item) => {
                try {
                    const result = await processor(item);
                    return { item, result };
                } catch (error) {
                    const err = error instanceof Error ? error : new Error(String(error));
                    if (failFast) throw err;
                    return { item, error: err };
                }
            });

            const batchResults = await Promise.all(batchPromises);
            results.push(...batchResults);
            
            if (progressCallback) {
                progressCallback(results.length, items.length);
            }
        }

        return results;
    }
}

// Custom exception class
class ValidationException extends Error {
    constructor(
        message: string,
        public validationErrors: ValidationError[]
    ) {
        super(message);
        this.name = 'ValidationException';
    }

    getErrorsForField(field: string): ValidationError[] {
        return this.validationErrors.filter(error => error.field === field);
    }

    hasErrors(): boolean {
        return this.validationErrors.length > 0;
    }
}

// Example concrete service implementation
interface User {
    id: string;
    email: string;
    name: string;
    createdAt: Date;
    updatedAt: Date;
}

interface CreateUserDto {
    email: string;
    name: string;
}

interface UpdateUserDto {
    name?: string;
    email?: string;
}

class UserService extends BaseService<User, CreateUserDto, UpdateUserDto> {
    async validateCreate(dto: CreateUserDto): Promise<ValidationError[]> {
        const errors: ValidationError[] = [];

        if (!dto.email || !dto.email.includes('@')) {
            errors.push({
                field: 'email',
                message: 'Valid email is required',
                code: 'INVALID_EMAIL'
            });
        }

        if (!dto.name || dto.name.length < 2) {
            errors.push({
                field: 'name',
                message: 'Name must be at least 2 characters',
                code: 'INVALID_NAME'
            });
        }

        return errors;
    }

    async validateUpdate(dto: UpdateUserDto): Promise<ValidationError[]> {
        const errors: ValidationError[] = [];

        if (dto.email && !dto.email.includes('@')) {
            errors.push({
                field: 'email',
                message: 'Valid email is required',
                code: 'INVALID_EMAIL'
            });
        }

        if (dto.name !== undefined && dto.name.length < 2) {
            errors.push({
                field: 'name',
                message: 'Name must be at least 2 characters',
                code: 'INVALID_NAME'
            });
        }

        return errors;
    }

    mapToModel(dto: CreateUserDto | UpdateUserDto): Partial<User> {
        return {
            email: dto.email,
            name: dto.name,
            updatedAt: new Date()
        };
    }

    // Service-specific method with complex type inference
    async getUsersWithActivity<TActivity>(
        activityFetcher: (userId: string) => Promise<TActivity>
    ): Promise<Array<User & { activity: TActivity }>> {
        const users = await this.repository.findMany({});
        
        return await this.bulkProcess(
            users,
            async (user) => {
                const activity = await activityFetcher(user.id);
                return { ...user, activity };
            },
            { concurrency: 3 }
        ).then(results => 
            results
                .filter(result => result.result && !result.error)
                .map(result => result.result!)
        );
    }
}

// Export all types and classes
export {
    StateManager,
    ApiClient,
    RequestBuilder,
    ApiError,
    BaseService,
    UserService,
    ValidationException,
    DataProcessing
};

export type {
    DeepPartial,
    RequireAtLeastOne,
    ApiResponse,
    ValidationError,
    EventName,
    HandlerName,
    ApiEndpoint,
    Repository,
    User,
    CreateUserDto,
    UpdateUserDto
};
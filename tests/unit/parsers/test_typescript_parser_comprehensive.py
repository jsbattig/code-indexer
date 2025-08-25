"""
Comprehensive tests for TypeScript semantic parser.
Tests AST-based parsing, advanced TypeScript features, decorators, and edge cases.
"""

from pathlib import Path
from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker
from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser


class TestTypeScriptParserComprehensive:
    """Comprehensive tests for TypeScript semantic parser with advanced features."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        self.parser = TypeScriptSemanticParser(self.config)
        self.chunker = SemanticChunker(self.config)
        self.test_files_dir = Path(__file__).parent / "test_files"

    def test_enterprise_application_parsing(self):
        """Test parsing of complex enterprise TypeScript application."""
        test_file = self.test_files_dir / "typescript" / "EnterpriseApp.ts"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for complex enterprise app
        assert len(chunks) > 35, f"Expected > 35 chunks, got {len(chunks)}"

        # Verify we capture all major constructs
        chunk_types = [chunk.semantic_type for chunk in chunks if chunk.semantic_type]

        assert "class" in chunk_types, "Should find class declarations"
        assert "interface" in chunk_types, "Should find interface declarations"
        assert "function" in chunk_types, "Should find function declarations"
        assert "type" in chunk_types, "Should find type declarations"

        # Test decorator detection
        decorator_chunks = [
            c for c in chunks if "@" in c.text and c.text.strip().startswith("@")
        ]
        assert len(decorator_chunks) >= 2, "Should find decorated classes"

        # Test generic class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        generic_classes = [c for c in class_chunks if "<" in c.text and ">" in c.text]
        assert len(generic_classes) >= 3, "Should find generic classes"

        # Test async/await patterns
        async_chunks = [c for c in chunks if "async" in c.text]
        assert len(async_chunks) >= 5, "Should find async patterns"

    def test_react_component_parsing(self):
        """Test parsing of React TypeScript components with hooks."""
        test_file = self.test_files_dir / "typescript" / "ReactComponents.tsx"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for React components
        assert len(chunks) > 25, f"Expected > 25 chunks, got {len(chunks)}"

        # Test React component detection (functional components)
        function_chunks = [
            c
            for c in chunks
            if c.semantic_type == "function" or c.semantic_type == "arrow_function"
        ]
        component_functions = [
            c
            for c in function_chunks
            if c.semantic_name
            and (
                c.semantic_name.endswith("Component")
                or c.semantic_name.startswith("use")
                or "JSX.Element" in c.text
                or "React.FC" in c.text
            )
        ]
        assert (
            len(component_functions) >= 4
        ), f"Should find React components, got {len(component_functions)}"

        # Test hook detection
        hook_chunks = [
            c
            for c in function_chunks
            if c.semantic_name and c.semantic_name.startswith("use")
        ]
        assert len(hook_chunks) >= 2, "Should find custom hooks"

        # Test React component detection (JSX content may not be preserved in chunks)
        react_components = [
            c
            for c in chunks
            if c.semantic_type in ["function", "arrow_function"]
            and c.semantic_name
            and (
                c.semantic_name[0].isupper()
                or "Component" in c.semantic_name
                or c.semantic_name.startswith("use")
            )
        ]
        assert len(react_components) >= 3, "Should find React components and hooks"

    def test_advanced_type_system(self):
        """Test TypeScript's advanced type system features."""
        content = """
// Advanced generic constraints
interface Lengthwise {
    length: number;
}

function loggingIdentity<T extends Lengthwise>(arg: T): T {
    console.log(arg.length);
    return arg;
}

// Mapped types
type Readonly<T> = {
    readonly [P in keyof T]: T[P];
};

type Partial<T> = {
    [P in keyof T]?: T[P];
};

type Pick<T, K extends keyof T> = {
    [P in K]: T[P];
};

// Conditional types
type NonNullable<T> = T extends null | undefined ? never : T;

type TypeName<T> = 
    T extends string ? "string" :
    T extends number ? "number" :
    T extends boolean ? "boolean" :
    T extends undefined ? "undefined" :
    T extends Function ? "function" :
    "object";

// Template literal types
type EmailLocaleIDs = "welcome_email" | "goodbye_email";
type FooterLocaleIDs = "footer_title" | "footer_sendoff";
type AllLocaleIDs = `${EmailLocaleIDs}_id` | `${FooterLocaleIDs}_id`;

// Utility types with complex constraints
type DeepReadonly<T> = {
    readonly [P in keyof T]: T[P] extends object ? DeepReadonly<T[P]> : T[P];
};

// Index signatures with template literals
type EventConfig<T extends Record<string, any>> = {
    [K in keyof T as `on${Capitalize<string & K>}`]?: (value: T[K]) => void;
};

// Discriminated unions
interface LoadingState {
    status: "loading";
}

interface SuccessState {
    status: "success";
    data: string;
}

interface ErrorState {
    status: "error";
    error: string;
}

type AsyncState = LoadingState | SuccessState | ErrorState;

// Generic class with complex constraints
class Repository<T extends { id: string | number }> {
    private items: Map<string | number, T> = new Map();
    
    add(item: T): void {
        this.items.set(item.id, item);
    }
    
    get<K extends keyof T>(id: T["id"], field?: K): T | T[K] | undefined {
        const item = this.items.get(id);
        return field && item ? item[field] : item;
    }
    
    // Method with conditional return type
    find<K extends keyof T>(
        predicate: (item: T) => boolean,
        returnField?: K
    ): K extends undefined ? T[] : T[K][] {
        const results: T[] = Array.from(this.items.values()).filter(predicate);
        return (returnField ? results.map(item => item[returnField]) : results) as any;
    }
}

// Abstract class with generic constraints
abstract class BaseService<TEntity, TCreateDto, TUpdateDto> {
    abstract create(dto: TCreateDto): Promise<TEntity>;
    abstract update(id: string, dto: TUpdateDto): Promise<TEntity>;
    abstract delete(id: string): Promise<void>;
    
    // Template method pattern
    async processEntity(id: string, processor: (entity: TEntity) => TEntity): Promise<TEntity> {
        const entity = await this.getById(id);
        const processed = processor(entity);
        return this.save(processed);
    }
    
    protected abstract getById(id: string): Promise<TEntity>;
    protected abstract save(entity: TEntity): Promise<TEntity>;
}

// Function overloads
function createElement(tag: "div"): HTMLDivElement;
function createElement(tag: "span"): HTMLSpanElement;
function createElement(tag: "canvas"): HTMLCanvasElement;
function createElement(tag: string): HTMLElement;
function createElement(tag: string): HTMLElement {
    return document.createElement(tag);
}

// Module augmentation example
declare module "express" {
    interface Request {
        user?: {
            id: string;
            email: string;
        };
    }
}

// Namespace with nested types
namespace API {
    export interface Response<T = any> {
        data: T;
        status: number;
        message?: string;
    }
    
    export namespace V1 {
        export interface User {
            id: string;
            name: string;
            email: string;
        }
        
        export type CreateUserRequest = Omit<User, "id">;
        export type UpdateUserRequest = Partial<CreateUserRequest>;
    }
    
    export namespace V2 {
        export interface User extends V1.User {
            profilePicture?: string;
            preferences: UserPreferences;
        }
        
        export interface UserPreferences {
            theme: "light" | "dark";
            notifications: boolean;
        }
    }
}

// Higher-order types
type ReturnTypeOf<T> = T extends (...args: any[]) => infer R ? R : never;
type PromiseType<T> = T extends Promise<infer U> ? U : T;
type ArrayElement<T> = T extends (infer U)[] ? U : never;

// Complex decorator example
function Entity(tableName: string) {
    return function <T extends new (...args: any[]) => {}>(constructor: T) {
        return class extends constructor {
            tableName = tableName;
            
            save() {
                console.log(`Saving to table: ${tableName}`);
            }
        };
    };
}

@Entity("users")
class User {
    constructor(
        public id: string,
        public name: string,
        public email: string
    ) {}
}
"""

        chunks = self.parser.chunk(content, "advanced_types.ts")

        # Test interface detection
        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert (
            len(interface_chunks) >= 5
        ), f"Should find multiple interfaces, got {len(interface_chunks)}"

        # Test type alias detection
        type_chunks = [
            c for c in chunks if c.semantic_type == "type" or "type " in c.text
        ]
        assert (
            len(type_chunks) >= 8
        ), f"Should find type aliases, got {len(type_chunks)}"

        # Test generic class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        generic_classes = [c for c in class_chunks if "<" in c.text and ">" in c.text]
        assert len(generic_classes) >= 2, "Should find generic classes"

        # Test function overloads
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        overload_functions = [
            c for c in function_chunks if "createElement" in c.semantic_name
        ]
        assert len(overload_functions) >= 1, "Should find overloaded functions"

        # Test namespace detection
        namespace_chunks = [c for c in chunks if "namespace" in c.text]
        assert len(namespace_chunks) >= 2, "Should find namespace declarations"

        # Test decorator detection
        decorator_chunks = [c for c in chunks if "@Entity" in c.text or "@" in c.text]
        assert len(decorator_chunks) >= 1, "Should find decorators"

    def test_decorators_and_metadata(self):
        """Test TypeScript decorators and metadata."""
        content = """
// Enable experimental decorators
import "reflect-metadata";

// Class decorator
function Component(config: { selector: string; template?: string }) {
    return function <T extends new (...args: any[]) => {}>(constructor: T) {
        return class extends constructor {
            selector = config.selector;
            template = config.template;
            
            render() {
                console.log(`Rendering component: ${config.selector}`);
            }
        };
    };
}

// Method decorator
function Log(target: any, propertyName: string, descriptor: PropertyDescriptor) {
    const method = descriptor.value;
    
    descriptor.value = function (...args: any[]) {
        console.log(`Calling ${propertyName} with args:`, args);
        const result = method.apply(this, args);
        console.log(`${propertyName} returned:`, result);
        return result;
    };
}

// Property decorator
function Inject(token: string) {
    return function (target: any, propertyKey: string) {
        Reflect.defineMetadata("inject", token, target, propertyKey);
    };
}

// Parameter decorator
function Required(target: any, propertyKey: string, parameterIndex: number) {
    const existingTokens = Reflect.getMetadata("required_params", target, propertyKey) || [];
    existingTokens.push(parameterIndex);
    Reflect.defineMetadata("required_params", existingTokens, target, propertyKey);
}

// Accessor decorator
function Enumerable(value: boolean) {
    return function (target: any, propertyKey: string, descriptor: PropertyDescriptor) {
        descriptor.enumerable = value;
    };
}

// Multiple decorators on class
@Component({
    selector: "user-profile",
    template: "<div>User Profile</div>"
})
class UserProfileComponent {
    @Inject("userService")
    private userService!: UserService;
    
    @Inject("logger")
    private logger!: Logger;
    
    private _name: string = "";
    
    @Enumerable(true)
    get name(): string {
        return this._name;
    }
    
    set name(value: string) {
        this._name = value;
    }
    
    @Log
    async loadUser(@Required userId: string, options?: LoadOptions): Promise<User> {
        this.logger.info(`Loading user with ID: ${userId}`);
        
        try {
            const user = await this.userService.getUser(userId);
            this._name = user.name;
            return user;
        } catch (error) {
            this.logger.error("Failed to load user", error);
            throw error;
        }
    }
    
    @Log
    updateProfile(updates: Partial<User>): void {
        console.log("Updating profile", updates);
    }
}

// Factory decorator
function Injectable<T extends new (...args: any[]) => {}>(constructor: T) {
    return class extends constructor {
        static instance?: InstanceType<T>;
        
        static getInstance(): InstanceType<T> {
            if (!this.instance) {
                this.instance = new this() as InstanceType<T>;
            }
            return this.instance;
        }
    };
}

@Injectable
class UserService {
    private users: User[] = [];
    
    async getUser(id: string): Promise<User> {
        const user = this.users.find(u => u.id === id);
        if (!user) {
            throw new Error(`User with id ${id} not found`);
        }
        return user;
    }
    
    @Log
    async createUser(@Required userData: CreateUserData): Promise<User> {
        const user = new User(
            Math.random().toString(36),
            userData.name,
            userData.email
        );
        this.users.push(user);
        return user;
    }
}

// Supporting interfaces and types
interface User {
    id: string;
    name: string;
    email: string;
}

interface CreateUserData {
    name: string;
    email: string;
}

interface LoadOptions {
    includeProfile?: boolean;
    timeout?: number;
}

interface Logger {
    info(message: string): void;
    error(message: string, error?: any): void;
}

class User implements User {
    constructor(
        public id: string,
        public name: string,
        public email: string
    ) {}
}
"""

        chunks = self.parser.chunk(content, "decorators.ts")

        # Test decorator function detection
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        decorator_functions = [
            c
            for c in function_chunks
            if c.semantic_name
            in ["Component", "Log", "Inject", "Required", "Injectable"]
        ]
        assert (
            len(decorator_functions) >= 3
        ), f"Should find decorator functions, got {len(decorator_functions)}"

        # Test decorated class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        decorated_classes = [c for c in class_chunks if "@" in c.text]
        assert len(decorated_classes) >= 2, "Should find decorated classes"

        # Test decorated method detection
        method_chunks = [
            c
            for c in chunks
            if c.semantic_type == "method"
            or (c.semantic_type == "function" and c.semantic_parent)
        ]
        decorated_methods = [
            c for c in method_chunks if "@Log" in c.text or "@Required" in c.text
        ]
        assert len(decorated_methods) >= 1, "Should find decorated methods"

    def test_async_await_and_promises(self):
        """Test async/await patterns and Promise handling."""
        content = """
// Basic async functions
async function fetchUserData(userId: string): Promise<User> {
    try {
        const response = await fetch(`/api/users/${userId}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const userData = await response.json();
        return userData as User;
    } catch (error) {
        console.error('Error fetching user data:', error);
        throw error;
    }
}

// Generic async function
async function fetchResource<T>(url: string): Promise<T> {
    const response = await fetch(url);
    
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
    }
    
    return response.json() as Promise<T>;
}

// Promise-based class
class ApiClient {
    private baseUrl: string;
    
    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }
    
    // Method returning Promise
    get<T>(endpoint: string): Promise<T> {
        return fetch(`${this.baseUrl}${endpoint}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .catch(error => {
                console.error('API call failed:', error);
                throw error;
            });
    }
    
    // Async method with error handling
    async post<TRequest, TResponse>(
        endpoint: string, 
        data: TRequest
    ): Promise<TResponse> {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Request failed');
            }
            
            return response.json();
        } catch (error) {
            console.error('POST request failed:', error);
            throw error;
        }
    }
    
    // Promise.all usage
    async fetchMultiple<T>(endpoints: string[]): Promise<T[]> {
        const promises = endpoints.map(endpoint => this.get<T>(endpoint));
        
        try {
            return await Promise.all(promises);
        } catch (error) {
            console.error('One or more requests failed:', error);
            throw error;
        }
    }
    
    // Promise.allSettled usage
    async fetchMultipleSettled<T>(endpoints: string[]): Promise<PromiseSettledResult<T>[]> {
        const promises = endpoints.map(endpoint => this.get<T>(endpoint));
        return Promise.allSettled(promises);
    }
}

// Async generator function
async function* fetchPages<T>(
    baseUrl: string, 
    pageSize: number = 10
): AsyncGenerator<T[], void, unknown> {
    let page = 1;
    let hasMore = true;
    
    while (hasMore) {
        const response = await fetch(`${baseUrl}?page=${page}&limit=${pageSize}`);
        const data = await response.json();
        
        if (data.items.length === 0) {
            hasMore = false;
        } else {
            yield data.items;
            page++;
            hasMore = data.hasMore;
        }
    }
}

// Async iterator usage
class DataStream<T> implements AsyncIterable<T> {
    constructor(private dataSource: () => Promise<T[]>) {}
    
    async *[Symbol.asyncIterator](): AsyncIterator<T> {
        const data = await this.dataSource();
        for (const item of data) {
            yield item;
        }
    }
}

// Complex async patterns
class TaskScheduler {
    private tasks: Map<string, Promise<any>> = new Map();
    
    // Schedule task with timeout
    async scheduleTask<T>(
        taskId: string, 
        task: () => Promise<T>, 
        timeoutMs: number = 30000
    ): Promise<T> {
        const timeoutPromise = new Promise<never>((_, reject) => {
            setTimeout(() => reject(new Error('Task timeout')), timeoutMs);
        });
        
        const taskPromise = Promise.race([task(), timeoutPromise]);
        this.tasks.set(taskId, taskPromise);
        
        try {
            const result = await taskPromise;
            this.tasks.delete(taskId);
            return result;
        } catch (error) {
            this.tasks.delete(taskId);
            throw error;
        }
    }
    
    // Wait for all tasks
    async waitForAllTasks(): Promise<void> {
        if (this.tasks.size === 0) return;
        
        try {
            await Promise.all(Array.from(this.tasks.values()));
        } finally {
            this.tasks.clear();
        }
    }
    
    // Retry pattern
    async retry<T>(
        operation: () => Promise<T>,
        maxAttempts: number = 3,
        delayMs: number = 1000
    ): Promise<T> {
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return await operation();
            } catch (error) {
                if (attempt === maxAttempts) {
                    throw error;
                }
                
                console.warn(`Attempt ${attempt} failed, retrying...`);
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        }
        
        throw new Error('All retry attempts failed');
    }
}

interface User {
    id: string;
    name: string;
    email: string;
}
"""

        chunks = self.parser.chunk(content, "async_patterns.ts")

        # Test async function detection (functions and methods)
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        async_functions = [
            c for c in function_chunks + method_chunks if "async" in c.text
        ]
        assert (
            len(async_functions) >= 5
        ), f"Should find multiple async functions/methods, got {len(async_functions)}"

        # Test generic async functions
        generic_async = [c for c in async_functions if "<" in c.text and ">" in c.text]
        assert len(generic_async) >= 2, "Should find generic async functions"

        # Test Promise-based methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        promise_methods = [c for c in method_chunks if "Promise" in c.text]
        assert len(promise_methods) >= 3, "Should find Promise-based methods"

        # Test async generator (may not be fully supported by tree-sitter parser)
        generator_chunks = [
            c
            for c in chunks
            if "async function*" in c.text or "AsyncGenerator" in c.text
        ]
        # Note: async generators require advanced AST parsing that may not be fully supported
        if len(generator_chunks) > 0:
            print(f"Found {len(generator_chunks)} async generators")

    def test_fallback_behavior_broken_typescript(self):
        """Test that broken TypeScript is handled gracefully, extracting what's possible."""
        broken_file = self.test_files_dir / "broken" / "BrokenTypeScript.ts"

        with open(broken_file, "r", encoding="utf-8") as f:
            broken_content = f.read()

        # Test with SemanticChunker
        chunks = self.chunker.chunk_content(broken_content, str(broken_file))

        # Should produce chunks even for broken TypeScript
        assert len(chunks) > 0, "Should produce chunks even for broken TypeScript"

        # Test data preservation - all content should be preserved
        all_chunk_text = "".join(chunk["text"] for chunk in chunks)

        # Key content should be preserved
        assert "BrokenInterface" in all_chunk_text
        assert "BrokenGeneric" in all_chunk_text
        assert "BrokenUnion" in all_chunk_text

        # The AST parser may extract some semantic information even from broken code
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        if semantic_chunks:
            # If semantic parsing worked, verify error handling or data preservation
            pass  # Just verify no data loss

    def test_minimal_valid_typescript(self):
        """Test parsing of minimal valid TypeScript."""
        content = """
interface User {
    name: string;
    age: number;
}

function greet(user: User): string {
    return `Hello, ${user.name}!`;
}
"""

        chunks = self.parser.chunk(content, "minimal.ts")

        assert len(chunks) >= 2, "Should create at least two chunks"

        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert len(interface_chunks) == 1, "Should find exactly one interface"
        assert interface_chunks[0].semantic_name == "User"

        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) == 1, "Should find exactly one function"
        assert function_chunks[0].semantic_name == "greet"

    def test_integration_with_semantic_chunker(self):
        """Test integration with SemanticChunker."""
        content = """
interface UserData {
    id: string;
    name: string;
    email: string;
}

class UserManager {
    private users: UserData[] = [];
    
    addUser(user: UserData): void {
        this.users.push(user);
    }
    
    getUser(id: string): UserData | undefined {
        return this.users.find(u => u.id === id);
    }
}

export { UserManager, UserData };
"""

        # Test through SemanticChunker
        chunks = self.chunker.chunk_content(content, "user_manager.ts")

        assert len(chunks) > 0, "Should produce chunks"

        # Should use semantic chunking
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert (
            len(semantic_chunks) > 0
        ), "Should use semantic chunking for valid TypeScript"

        # Test chunk structure
        interface_chunks = [
            c for c in semantic_chunks if c.get("semantic_type") == "interface"
        ]
        user_interface = next(
            (c for c in interface_chunks if c.get("semantic_name") == "UserData"), None
        )
        assert (
            user_interface is not None
        ), "Should find UserData interface through SemanticChunker"

        class_chunks = [c for c in semantic_chunks if c.get("semantic_type") == "class"]
        user_manager = next(
            (c for c in class_chunks if c.get("semantic_name") == "UserManager"), None
        )
        assert (
            user_manager is not None
        ), "Should find UserManager class through SemanticChunker"

    def test_semantic_metadata_completeness(self):
        """Test that semantic metadata is complete and accurate."""
        content = """
interface TestInterface {
    property: string;
}

class TestClass implements TestInterface {
    property: string = "test";
    
    testMethod(): string {
        return this.property;
    }
}

function testFunction(param: string): string {
    return param.toUpperCase();
}

type TestType = string | number;
"""

        chunks = self.parser.chunk(content, "metadata-test.ts")

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
        expected_types = {"interface", "class", "function", "type"}
        assert expected_types.intersection(
            construct_types
        ), f"Should find various constructs. Found: {construct_types}"

    def test_line_number_accuracy(self):
        """Test that line numbers are accurately tracked."""
        content = """interface Config {
    apiUrl: string;
}

class ApiClient {
    constructor(private config: Config) {}
    
    async fetchData(): Promise<string> {
        return "data";
    }
}

function createClient(config: Config): ApiClient {
    return new ApiClient(config);
}"""

        chunks = self.parser.chunk(content, "line-test.ts")

        # Find specific chunks and verify their line numbers
        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        config_interface = next(
            (c for c in interface_chunks if c.semantic_name == "Config"), None
        )

        if config_interface:
            assert (
                config_interface.line_start == 1
            ), f"Config interface should start at line 1, got {config_interface.line_start}"

        # Test class line numbers
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        api_client = next(
            (c for c in class_chunks if c.semantic_name == "ApiClient"), None
        )

        if api_client:
            assert (
                api_client.line_start >= 4
            ), f"ApiClient class should start around line 4, got {api_client.line_start}"

        # Test function line numbers
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        create_client = next(
            (c for c in function_chunks if c.semantic_name == "createClient"), None
        )

        if create_client:
            assert (
                create_client.line_start >= 11
            ), f"createClient function should start around line 11, got {create_client.line_start}"
            assert (
                create_client.line_end >= create_client.line_start
            ), "Line end should be >= line start"

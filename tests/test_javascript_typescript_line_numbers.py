#!/usr/bin/env python3
"""
Comprehensive tests for JavaScript/TypeScript parser line number accuracy.

This test suite verifies that JavaScript and TypeScript semantic parsers
report accurate line numbers that match the actual content boundaries.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser
from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser


class TestJavaScriptTypeScriptLineNumbers:
    """Test line number accuracy for JavaScript and TypeScript parsers."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        config = IndexingConfig()
        config.chunk_size = 2000  # Large enough to avoid splitting
        config.chunk_overlap = 100
        return config

    @pytest.fixture
    def js_parser(self, config):
        """Create JavaScript parser."""
        return JavaScriptSemanticParser(config)

    @pytest.fixture
    def ts_parser(self, config):
        """Create TypeScript parser."""
        return TypeScriptSemanticParser(config)

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

    def test_javascript_function_definitions(self, js_parser):
        """Test JavaScript function definitions line number accuracy."""
        code = """// JavaScript test file
import { utils } from './utils';

function regularFunction(param1, param2) {
    console.log("Regular function");
    return param1 + param2;
}

async function asyncFunction(data) {
    console.log("Async function");
    const result = await processData(data);
    return result;
}

const arrowFunction = (x, y) => {
    console.log("Arrow function");
    return x * y;
};

const singleLineArrow = (x) => x * 2;

function complexFunction(options = {}) {
    const {
        debug = false,
        timeout = 1000
    } = options;
    
    if (debug) {
        console.log('Debug mode enabled');
    }
    
    return new Promise((resolve) => {
        setTimeout(resolve, timeout);
    });
}"""

        chunks = js_parser.chunk(code, "test.js")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"JavaScript functions - chunk {i+1}"
            )

    def test_javascript_class_definitions(self, js_parser):
        """Test JavaScript class definitions line number accuracy."""
        code = """class BaseClass {
    constructor(name) {
        this.name = name;
        this.initialized = true;
    }
    
    getName() {
        return this.name;
    }
    
    async loadData() {
        const data = await fetch('/api/data');
        return data.json();
    }
}

class ExtendedClass extends BaseClass {
    constructor(name, type) {
        super(name);
        this.type = type;
    }
    
    static createDefault() {
        return new ExtendedClass('default', 'standard');
    }
    
    getFullInfo() {
        return {
            name: this.getName(),
            type: this.type,
            initialized: this.initialized
        };
    }
}

class ReactComponent extends React.Component {
    constructor(props) {
        super(props);
        this.state = { count: 0 };
    }
    
    render() {
        return (
            <div>
                <h1>{this.props.title}</h1>
                <p>Count: {this.state.count}</p>
            </div>
        );
    }
}"""

        chunks = js_parser.chunk(code, "classes.js")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"JavaScript classes - chunk {i+1}"
            )

    def test_javascript_object_methods(self, js_parser):
        """Test JavaScript object method definitions line number accuracy."""
        code = """const apiHandler = {
    baseUrl: 'https://api.example.com',
    
    get: function(endpoint) {
        return fetch(`${this.baseUrl}/${endpoint}`);
    },
    
    post(endpoint, data) {
        return fetch(`${this.baseUrl}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },
    
    async processResponse(response) {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
};

const utilities = {
    formatDate: (date) => {
        return new Intl.DateTimeFormat('en-US').format(date);
    },
    
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};"""

        chunks = js_parser.chunk(code, "objects.js")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"JavaScript objects - chunk {i+1}"
            )

    def test_typescript_interfaces(self, ts_parser):
        """Test TypeScript interface definitions line number accuracy."""
        code = """interface User {
    id: number;
    name: string;
    email: string;
    isActive: boolean;
}

interface ApiResponse<T> {
    data: T;
    status: number;
    message?: string;
    timestamp: Date;
}

interface ExtendedUser extends User {
    roles: string[];
    lastLogin?: Date;
    preferences: {
        theme: 'light' | 'dark';
        notifications: boolean;
    };
}

interface EventHandler<T = any> {
    (event: T): void;
}

interface DatabaseConfig {
    host: string;
    port: number;
    database: string;
    credentials: {
        username: string;
        password: string;
    };
    ssl?: boolean;
}"""

        chunks = ts_parser.chunk(code, "interfaces.ts")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"TypeScript interfaces - chunk {i+1}"
            )

    def test_typescript_types_and_enums(self, ts_parser):
        """Test TypeScript type aliases and enums line number accuracy."""
        code = """type Status = 'pending' | 'approved' | 'rejected';

type UserPreferences = {
    theme: 'light' | 'dark';
    language: string;
    notifications: boolean;
};

type ComplexType<T, K extends keyof T> = {
    [P in K]: T[P];
} & {
    metadata: {
        created: Date;
        updated: Date;
    };
};

enum Color {
    Red = 'red',
    Green = 'green',
    Blue = 'blue'
}

const enum Direction {
    Up = 1,
    Down,
    Left,
    Right
}

enum HttpStatus {
    OK = 200,
    BAD_REQUEST = 400,
    UNAUTHORIZED = 401,
    NOT_FOUND = 404,
    INTERNAL_SERVER_ERROR = 500
}

type ApiFunction<T> = (
    params: T
) => Promise<ApiResponse<T>>;

type EventMap = {
    click: MouseEvent;
    keydown: KeyboardEvent;
    load: Event;
};"""

        chunks = ts_parser.chunk(code, "types.ts")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"TypeScript types/enums - chunk {i+1}"
            )

    def test_typescript_classes_with_decorators(self, ts_parser):
        """Test TypeScript classes with decorators line number accuracy."""
        code = """import { Component, Injectable, Input } from 'framework';

@Component({
    selector: 'app-user',
    template: `
        <div>
            <h2>{{user.name}}</h2>
            <p>{{user.email}}</p>
        </div>
    `
})
class UserComponent {
    @Input() user: User;
    @Input() showDetails: boolean = false;
    
    private _isVisible: boolean = true;
    
    constructor(
        private userService: UserService,
        private logger: Logger
    ) {}
    
    ngOnInit(): void {
        this.logger.log('UserComponent initialized');
    }
    
    @HostListener('click', ['$event'])
    onClick(event: MouseEvent): void {
        console.log('Component clicked');
    }
    
    public async loadUserData(): Promise<void> {
        try {
            const userData = await this.userService.getUser(this.user.id);
            this.user = userData;
        } catch (error) {
            this.logger.error('Failed to load user data', error);
        }
    }
}

@Injectable({
    providedIn: 'root'
})
class DataService {
    private baseUrl = 'https://api.example.com';
    
    constructor(private http: HttpClient) {}
    
    async fetchData<T>(endpoint: string): Promise<T> {
        const response = await this.http.get<T>(`${this.baseUrl}/${endpoint}`);
        return response;
    }
}"""

        chunks = ts_parser.chunk(code, "components.ts")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"TypeScript decorators - chunk {i+1}"
            )

    def test_javascript_react_components(self, js_parser):
        """Test JavaScript React component detection and line number accuracy."""
        code = """import React, { useState, useEffect } from 'react';

function UserProfile({ userId }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        async function fetchUser() {
            try {
                const response = await fetch(`/api/users/${userId}`);
                const userData = await response.json();
                setUser(userData);
            } catch (error) {
                console.error('Failed to fetch user:', error);
            } finally {
                setLoading(false);
            }
        }
        
        fetchUser();
    }, [userId]);
    
    if (loading) {
        return <div>Loading...</div>;
    }
    
    return (
        <div className="user-profile">
            <h1>{user.name}</h1>
            <p>{user.email}</p>
        </div>
    );
}

const WelcomeMessage = (props) => {
    return (
        <div>
            <h2>Welcome, {props.userName}!</h2>
            <p>Thanks for joining our platform.</p>
        </div>
    );
};

class ClassComponent extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            count: 0
        };
    }
    
    handleClick = () => {
        this.setState({ count: this.state.count + 1 });
    }
    
    render() {
        return (
            <button onClick={this.handleClick}>
                Clicked {this.state.count} times
            </button>
        );
    }
}"""

        chunks = js_parser.chunk(code, "components.jsx")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"JavaScript React - chunk {i+1}"
            )

    def test_typescript_generic_functions(self, ts_parser):
        """Test TypeScript generic function definitions line number accuracy."""
        code = """function identity<T>(arg: T): T {
    return arg;
}

function createArray<T>(length: number, value: T): T[] {
    const result: T[] = [];
    for (let i = 0; i < length; i++) {
        result.push(value);
    }
    return result;
}

async function fetchAndProcess<T, R>(
    url: string,
    processor: (data: T) => R
): Promise<R> {
    const response = await fetch(url);
    const data: T = await response.json();
    return processor(data);
}

interface Repository<T> {
    findById(id: string): Promise<T | null>;
    save(entity: T): Promise<T>;
    delete(id: string): Promise<void>;
}

class GenericService<T extends { id: string }> implements Repository<T> {
    private items: Map<string, T> = new Map();
    
    async findById(id: string): Promise<T | null> {
        return this.items.get(id) || null;
    }
    
    async save(entity: T): Promise<T> {
        this.items.set(entity.id, entity);
        return entity;
    }
    
    async delete(id: string): Promise<void> {
        this.items.delete(id);
    }
    
    getAllItems(): T[] {
        return Array.from(this.items.values());
    }
}

type Mapper<T, R> = {
    map(input: T): R;
    mapArray(inputs: T[]): R[];
};

const stringMapper: Mapper<number, string> = {
    map: (input: number): string => input.toString(),
    mapArray: (inputs: number[]): string[] => inputs.map(n => n.toString())
};"""

        chunks = ts_parser.chunk(code, "generics.ts")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"TypeScript generics - chunk {i+1}"
            )

    def test_javascript_complex_structures(self, js_parser):
        """Test complex JavaScript structures line number accuracy."""
        code = """// Complex nested structures
const configManager = {
    settings: {
        api: {
            baseUrl: 'https://api.example.com',
            timeout: 5000,
            retries: 3
        },
        ui: {
            theme: 'dark',
            animations: true
        }
    },
    
    init: function() {
        console.log('Config manager initialized');
        this.loadSettings();
    },
    
    loadSettings: async function() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();
            Object.assign(this.settings, config);
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    },
    
    updateSetting: function(path, value) {
        const keys = path.split('.');
        let current = this.settings;
        
        for (let i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]]) {
                current[keys[i]] = {};
            }
            current = current[keys[i]];
        }
        
        current[keys[keys.length - 1]] = value;
    }
};

function createModule(name, dependencies = []) {
    const moduleCache = new Map();
    
    return {
        name,
        dependencies,
        
        register: function(key, factory) {
            if (typeof factory !== 'function') {
                throw new Error('Factory must be a function');
            }
            moduleCache.set(key, factory);
        },
        
        resolve: function(key) {
            if (!moduleCache.has(key)) {
                throw new Error(`Module ${key} not found`);
            }
            
            const factory = moduleCache.get(key);
            return factory();
        },
        
        list: () => Array.from(moduleCache.keys())
    };
}

// IIFE pattern
(function(global) {
    'use strict';
    
    const VERSION = '1.0.0';
    
    function Library() {
        this.version = VERSION;
        this.modules = [];
    }
    
    Library.prototype.addModule = function(module) {
        this.modules.push(module);
    };
    
    global.MyLibrary = Library;
    
})(typeof window !== 'undefined' ? window : global);"""

        chunks = js_parser.chunk(code, "complex.js")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"JavaScript complex - chunk {i+1}"
            )

    def test_typescript_edge_cases(self, ts_parser):
        """Test TypeScript edge cases for line number accuracy."""
        code = """// Edge cases for TypeScript parsing

// Namespace
namespace Utils {
    export interface Config {
        debug: boolean;
    }
    
    export function log(message: string): void {
        console.log(message);
    }
}

// Module with re-exports
export { UserService } from './user.service';
export * from './types';

// Conditional types
type NonNullable<T> = T extends null | undefined ? never : T;

type ReturnType<T extends (...args: any) => any> = T extends (
    ...args: any
) => infer R
    ? R
    : any;

// Mapped types
type Partial<T> = {
    [P in keyof T]?: T[P];
};

type Record<K extends keyof any, T> = {
    [P in K]: T;
};

// Function overloads
function processValue(value: string): string;
function processValue(value: number): number;
function processValue(value: boolean): boolean;
function processValue(value: any): any {
    return value;
}

// Class with complex inheritance
abstract class AbstractProcessor<T> {
    protected abstract process(item: T): Promise<T>;
    
    async processAll(items: T[]): Promise<T[]> {
        const results: T[] = [];
        for (const item of items) {
            const processed = await this.process(item);
            results.push(processed);
        }
        return results;
    }
}

class StringProcessor extends AbstractProcessor<string> {
    protected async process(item: string): Promise<string> {
        return item.toUpperCase();
    }
}

// Decorator factory
function Logger(target: any, propertyKey: string, descriptor: PropertyDescriptor) {
    const originalMethod = descriptor.value;
    
    descriptor.value = function(...args: any[]) {
        console.log(`Calling ${propertyKey} with args:`, args);
        const result = originalMethod.apply(this, args);
        console.log(`${propertyKey} returned:`, result);
        return result;
    };
    
    return descriptor;
}

class Example {
    @Logger
    calculate(x: number, y: number): number {
        return x + y;
    }
}"""

        chunks = ts_parser.chunk(code, "edge_cases.ts")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"TypeScript edge cases - chunk {i+1}"
            )

    def test_jsx_tsx_components(self, js_parser, ts_parser):
        """Test JSX/TSX component line number accuracy."""
        jsx_code = """import React from 'react';
import { useState } from 'react';

function TodoList({ initialTodos = [] }) {
    const [todos, setTodos] = useState(initialTodos);
    const [newTodo, setNewTodo] = useState('');
    
    const addTodo = () => {
        if (newTodo.trim()) {
            setTodos([...todos, {
                id: Date.now(),
                text: newTodo,
                completed: false
            }]);
            setNewTodo('');
        }
    };
    
    const toggleTodo = (id) => {
        setTodos(todos.map(todo =>
            todo.id === id ? { ...todo, completed: !todo.completed } : todo
        ));
    };
    
    return (
        <div className="todo-list">
            <h1>Todo List</h1>
            <div className="add-todo">
                <input
                    type="text"
                    value={newTodo}
                    onChange={(e) => setNewTodo(e.target.value)}
                    placeholder="Add new todo..."
                />
                <button onClick={addTodo}>Add</button>
            </div>
            <ul>
                {todos.map(todo => (
                    <li key={todo.id} className={todo.completed ? 'completed' : ''}>
                        <span onClick={() => toggleTodo(todo.id)}>
                            {todo.text}
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export default TodoList;"""

        tsx_code = """import React, { useState, useEffect } from 'react';

interface User {
    id: number;
    name: string;
    email: string;
}

interface Props {
    userId: number;
    onUserLoad?: (user: User) => void;
}

const UserProfile: React.FC<Props> = ({ userId, onUserLoad }) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    
    useEffect(() => {
        const fetchUser = async (): Promise<void> => {
            try {
                setLoading(true);
                setError(null);
                
                const response = await fetch(`/api/users/${userId}`);
                if (!response.ok) {
                    throw new Error('Failed to fetch user');
                }
                
                const userData: User = await response.json();
                setUser(userData);
                
                if (onUserLoad) {
                    onUserLoad(userData);
                }
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Unknown error');
            } finally {
                setLoading(false);
            }
        };
        
        fetchUser();
    }, [userId, onUserLoad]);
    
    if (loading) {
        return <div className="loading">Loading user...</div>;
    }
    
    if (error) {
        return <div className="error">Error: {error}</div>;
    }
    
    if (!user) {
        return <div className="no-user">User not found</div>;
    }
    
    return (
        <div className="user-profile">
            <h2>{user.name}</h2>
            <p>Email: {user.email}</p>
            <p>ID: {user.id}</p>
        </div>
    );
};

export default UserProfile;"""

        # Test JSX
        jsx_chunks = js_parser.chunk(jsx_code, "TodoList.jsx")
        assert len(jsx_chunks) > 0, "Expected at least one JSX chunk"

        for i, chunk in enumerate(jsx_chunks):
            self._verify_chunk_line_numbers(
                chunk, jsx_code, f"JSX component - chunk {i+1}"
            )

        # Test TSX
        tsx_chunks = ts_parser.chunk(tsx_code, "UserProfile.tsx")
        assert len(tsx_chunks) > 0, "Expected at least one TSX chunk"

        for i, chunk in enumerate(tsx_chunks):
            self._verify_chunk_line_numbers(
                chunk, tsx_code, f"TSX component - chunk {i+1}"
            )

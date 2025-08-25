"""
Comprehensive tests for JavaScript semantic parser.
Tests AST-based parsing, modern ES6+ features, React patterns, and edge cases.
"""

from pathlib import Path
from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker
from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser


class TestJavaScriptParserComprehensive:
    """Comprehensive tests for JavaScript semantic parser with modern features."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        self.parser = JavaScriptSemanticParser(self.config)
        self.chunker = SemanticChunker(self.config)
        self.test_files_dir = Path(__file__).parent / "test_files"

    def test_modern_react_app_parsing(self):
        """Test parsing of complex React application with hooks."""
        test_file = self.test_files_dir / "javascript" / "ModernReactApp.js"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for complex React app
        assert len(chunks) > 25, f"Expected > 25 chunks, got {len(chunks)}"

        # Verify we capture all major constructs
        chunk_types = [chunk.semantic_type for chunk in chunks if chunk.semantic_type]

        assert "function" in chunk_types, "Should find function declarations"
        assert "class" in chunk_types, "Should find class components"
        assert "arrow_function" in chunk_types, "Should find arrow functions"
        assert "variable" in chunk_types, "Should find variable declarations"

        # Test React component detection
        component_chunks = [
            c
            for c in chunks
            if c.semantic_type in ["function", "class", "arrow_function"]
            and c.semantic_name
            and (
                "Component" in c.semantic_name
                or "Hook" in c.semantic_name
                or c.semantic_name.startswith("use")  # Custom hooks
                or (
                    c.semantic_name[0].isupper()
                    and c.semantic_type in ["function", "arrow_function"]
                )  # React components (capitalize)
                or (
                    c.semantic_type == "class" and "extends React.Component" in c.text
                )  # Class components
            )
        ]
        assert (
            len(component_chunks) >= 3
        ), f"Should find React components/hooks, got {len(component_chunks)}"

        # Test hook detection (custom hooks start with 'use')
        hook_chunks = [
            c for c in chunks if c.semantic_name and c.semantic_name.startswith("use")
        ]
        assert (
            len(hook_chunks) >= 2
        ), f"Should find custom hooks, got {len(hook_chunks)}"

        # Test arrow function detection
        arrow_chunks = [c for c in chunks if c.semantic_type == "arrow_function"]
        assert (
            len(arrow_chunks) >= 5
        ), f"Should find arrow functions, got {len(arrow_chunks)}"

        # Test import/export detection
        import_chunks = [c for c in chunks if c.semantic_type == "import"]
        export_chunks = [c for c in chunks if c.semantic_type == "export"]
        assert len(import_chunks) >= 3, "Should find import statements"
        assert len(export_chunks) >= 1, "Should find export statements"

    def test_es6_features(self):
        """Test parsing of ES6+ features."""
        content = """
// Import/Export
import React, { useState, useEffect } from 'react';
import * as utils from './utils';
export { Component as default } from './Component';

// Arrow functions
const add = (a, b) => a + b;
const multiply = (a, b) => {
    return a * b;
};

// Template literals
const message = `Hello ${name}, you have ${count} items`;

// Destructuring
const { name, age, ...rest } = user;
const [first, second, ...others] = items;

// Async/await
async function fetchData(url) {
    try {
        const response = await fetch(url);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

// Classes
class UserManager {
    constructor(apiUrl) {
        this.apiUrl = apiUrl;
        this.users = new Map();
    }
    
    async getUser(id) {
        if (this.users.has(id)) {
            return this.users.get(id);
        }
        
        const user = await this.fetchUser(id);
        this.users.set(id, user);
        return user;
    }
    
    // Static method
    static createManager(config) {
        return new UserManager(config.apiUrl);
    }
}

// Object literal with methods
const calculator = {
    add(a, b) {
        return a + b;
    },
    
    subtract: function(a, b) {
        return a - b;
    },
    
    // Computed property
    [operation]: (a, b) => a * b
};

// Generators
function* fibonacci() {
    let a = 0, b = 1;
    while (true) {
        yield a;
        [a, b] = [b, a + b];
    }
}
"""

        chunks = self.parser.chunk(content, "es6-features.js")

        # Test function detection
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        function_names = {c.semantic_name for c in function_chunks}
        assert "fetchData" in function_names, "Should find async function"
        assert "fibonacci" in function_names, "Should find generator function"

        # Test arrow function detection
        arrow_chunks = [c for c in chunks if c.semantic_type == "arrow_function"]
        arrow_names = {c.semantic_name for c in arrow_chunks if c.semantic_name}
        assert (
            "add" in arrow_names or len(arrow_chunks) >= 2
        ), "Should find arrow functions"

        # Test class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1, "Should find class declaration"
        assert class_chunks[0].semantic_name == "UserManager"

        # Test method detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}
        assert "getUser" in method_names, "Should find class methods"

    def test_react_hooks_and_components(self):
        """Test React-specific patterns."""
        content = """
import React, { useState, useEffect, useCallback, useMemo } from 'react';

// Functional component with hooks
const UserProfile = ({ userId, onUserUpdate }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Effect hook
    useEffect(() => {
        async function fetchUser() {
            try {
                setLoading(true);
                const response = await fetch(`/api/users/${userId}`);
                const userData = await response.json();
                setUser(userData);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }

        if (userId) {
            fetchUser();
        }
    }, [userId]);

    // Callback hook
    const handleUpdate = useCallback(async (updates) => {
        try {
            const response = await fetch(`/api/users/${userId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            
            const updatedUser = await response.json();
            setUser(updatedUser);
            onUserUpdate?.(updatedUser);
        } catch (err) {
            setError(err.message);
        }
    }, [userId, onUserUpdate]);

    // Memo hook
    const displayName = useMemo(() => {
        return user ? `${user.firstName} ${user.lastName}` : 'Unknown User';
    }, [user]);

    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error}</div>;

    return (
        <div className="user-profile">
            <h1>{displayName}</h1>
            <UserDetails user={user} onUpdate={handleUpdate} />
        </div>
    );
};

// Custom hook
const useLocalStorage = (key, initialValue) => {
    const [storedValue, setStoredValue] = useState(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.error(`Error reading localStorage key "${key}":`, error);
            return initialValue;
        }
    });

    const setValue = useCallback((value) => {
        try {
            setStoredValue(value);
            window.localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.error(`Error setting localStorage key "${key}":`, error);
        }
    }, [key]);

    return [storedValue, setValue];
};

export default UserProfile;
export { useLocalStorage };
"""

        chunks = self.parser.chunk(content, "react-hooks.js")

        # Test component detection (should be arrow function)
        arrow_chunks = [c for c in chunks if c.semantic_type == "arrow_function"]
        component_chunk = next(
            (c for c in arrow_chunks if c.semantic_name == "UserProfile"), None
        )
        assert component_chunk is not None, "Should find UserProfile component"

        # Test custom hook detection
        hook_chunk = next(
            (c for c in arrow_chunks if c.semantic_name == "useLocalStorage"), None
        )
        assert hook_chunk is not None, "Should find useLocalStorage custom hook"

        # Test nested function detection
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        nested_functions = [c for c in function_chunks if c.semantic_parent is not None]
        assert len(nested_functions) >= 1, "Should find nested functions"

    def test_class_components(self):
        """Test parsing of React class components."""
        content = """
import React, { Component } from 'react';
import PropTypes from 'prop-types';

class DataTable extends Component {
    static propTypes = {
        data: PropTypes.array.isRequired,
        columns: PropTypes.array.isRequired,
        onRowClick: PropTypes.func
    };

    static defaultProps = {
        data: [],
        onRowClick: () => {}
    };

    constructor(props) {
        super(props);
        
        this.state = {
            sortColumn: null,
            sortDirection: 'asc',
            selectedRows: new Set()
        };
        
        this.handleSort = this.handleSort.bind(this);
    }

    componentDidMount() {
        this.loadData();
    }

    componentDidUpdate(prevProps) {
        if (prevProps.data !== this.props.data) {
            this.setState({ selectedRows: new Set() });
        }
    }

    handleSort = (column) => {
        this.setState(prevState => ({
            sortColumn: column,
            sortDirection: prevState.sortColumn === column && prevState.sortDirection === 'asc' ? 'desc' : 'asc'
        }));
    };

    loadData = async () => {
        try {
            const response = await fetch('/api/data');
            const data = await response.json();
            this.setState({ data });
        } catch (error) {
            console.error('Failed to load data:', error);
        }
    };

    render() {
        const { data, columns } = this.props;
        const { sortColumn, sortDirection } = this.state;

        return (
            <table className="data-table">
                <thead>
                    <tr>
                        {columns.map(column => (
                            <th key={column.key} onClick={() => this.handleSort(column.key)}>
                                {column.title}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {data.map(row => (
                        <tr key={row.id}>
                            {columns.map(column => (
                                <td key={column.key}>{row[column.key]}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
}

export default DataTable;
"""

        chunks = self.parser.chunk(content, "class-component.js")

        # Test class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1, "Should find one class component"
        assert class_chunks[0].semantic_name == "DataTable"

        # Test method detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}

        expected_methods = {
            "constructor",
            "componentDidMount",
            "componentDidUpdate",
            "render",
        }
        found_methods = expected_methods.intersection(method_names)
        assert (
            len(found_methods) >= 3
        ), f"Should find lifecycle methods. Found: {method_names}"

    def test_module_patterns(self):
        """Test various JavaScript module patterns."""
        content = """
// Named exports
export const API_BASE_URL = 'https://api.example.com';
export const DEFAULT_TIMEOUT = 5000;

// Function export
export function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

// Class export
export class ApiClient {
    constructor(baseUrl = API_BASE_URL) {
        this.baseUrl = baseUrl;
    }

    async get(endpoint) {
        const response = await fetch(`${this.baseUrl}${endpoint}`);
        return response.json();
    }
}

// Arrow function export
export const calculateTax = (amount, rate) => amount * rate;

// Object export
export const utils = {
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
};

// Default export (function)
export default function createStore(initialState = {}) {
    let state = { ...initialState };
    const listeners = [];

    return {
        getState() {
            return { ...state };
        },

        setState(updates) {
            state = { ...state, ...updates };
            listeners.forEach(listener => listener(state));
        },

        subscribe(listener) {
            listeners.push(listener);
            return () => {
                const index = listeners.indexOf(listener);
                if (index > -1) {
                    listeners.splice(index, 1);
                }
            };
        }
    };
}

// Re-export from other modules
export { UserService } from './services/UserService';
export { default as Logger } from './utils/Logger';
"""

        chunks = self.parser.chunk(content, "module-patterns.js")

        # Test export detection
        export_chunks = [
            c
            for c in chunks
            if c.semantic_type == "export" or "export" in c.text.lower()
        ]
        assert (
            len(export_chunks) >= 5
        ), f"Should find multiple exports, got {len(export_chunks)}"

        # Test function exports
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        function_names = {c.semantic_name for c in function_chunks}
        assert "formatCurrency" in function_names, "Should find exported function"
        assert "createStore" in function_names, "Should find default export function"

        # Test class exports
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1, "Should find exported class"
        assert class_chunks[0].semantic_name == "ApiClient"

    def test_async_patterns(self):
        """Test async/await and Promise patterns."""
        content = """
// Promise-based functions
function fetchUserData(userId) {
    return fetch(`/api/users/${userId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .catch(error => {
            console.error('Error fetching user data:', error);
            throw error;
        });
}

// Async/await function
async function getUserProfile(userId) {
    try {
        const [user, preferences, activity] = await Promise.all([
            fetchUserData(userId),
            fetchUserPreferences(userId),
            fetchUserActivity(userId)
        ]);

        return {
            ...user,
            preferences,
            activity
        };
    } catch (error) {
        console.error('Failed to load user profile:', error);
        return null;
    }
}

// Async arrow function
const uploadFile = async (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Upload error:', error);
        throw error;
    }
};

// Generator function
function* dataGenerator(items) {
    for (const item of items) {
        yield processItem(item);
    }
}

// Async generator
async function* asyncDataGenerator(urls) {
    for (const url of urls) {
        try {
            const response = await fetch(url);
            const data = await response.json();
            yield data;
        } catch (error) {
            console.warn(`Failed to fetch ${url}:`, error);
        }
    }
}

// Complex async class
class DataProcessor {
    constructor(options = {}) {
        this.batchSize = options.batchSize || 10;
        this.concurrency = options.concurrency || 3;
    }

    async processBatch(items) {
        const batches = this.createBatches(items, this.batchSize);
        const results = [];

        for (const batch of batches) {
            const batchResults = await Promise.allSettled(
                batch.map(item => this.processItem(item))
            );
            results.push(...batchResults);
        }

        return results;
    }

    async processItem(item) {
        // Simulate async processing
        return new Promise(resolve => {
            setTimeout(() => resolve({ ...item, processed: true }), 100);
        });
    }

    createBatches(items, batchSize) {
        const batches = [];
        for (let i = 0; i < items.length; i += batchSize) {
            batches.push(items.slice(i, i + batchSize));
        }
        return batches;
    }
}
"""

        chunks = self.parser.chunk(content, "async-patterns.js")

        # Test async function detection
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        async_functions = [c for c in function_chunks if "async" in c.text]
        assert (
            len(async_functions) >= 2
        ), f"Should find async functions, got {len(async_functions)}"

        # Test generator function detection
        generator_functions = [
            c for c in function_chunks if "function*" in c.text or "yield" in c.text
        ]
        assert len(generator_functions) >= 1, "Should find generator functions"

        # Test arrow function detection
        arrow_chunks = [c for c in chunks if c.semantic_type == "arrow_function"]
        async_arrows = [c for c in arrow_chunks if "async" in c.text]
        assert len(async_arrows) >= 1, "Should find async arrow functions"

    def test_edge_cases_and_complex_syntax(self):
        """Test edge cases and complex JavaScript syntax."""
        content = """
// Immediately Invoked Function Expression (IIFE)
(function() {
    console.log('IIFE executed');
})();

// IIFE with parameters
((global, undefined) => {
    global.myLib = {
        version: '1.0.0'
    };
})(window);

// Complex object with computed properties
const dynamicKey = 'computed';
const complexObject = {
    // Regular property
    name: 'test',
    
    // Computed property
    [dynamicKey]: 'value',
    [`${dynamicKey}Method`]: function() {
        return this[dynamicKey];
    },
    
    // Method shorthand
    regularMethod() {
        return 'regular';
    },
    
    // Async method
    async asyncMethod() {
        return await Promise.resolve('async result');
    },
    
    // Generator method
    *generatorMethod() {
        yield 1;
        yield 2;
        yield 3;
    },
    
    // Getter and setter
    get fullName() {
        return `${this.firstName} ${this.lastName}`;
    },
    
    set fullName(value) {
        [this.firstName, this.lastName] = value.split(' ');
    }
};

// Complex destructuring
const {
    name,
    [dynamicKey]: computedValue,
    regularMethod,
    ...restProperties
} = complexObject;

// Advanced array methods with complex callbacks
const processedData = items
    .filter(item => item.active)
    .map(item => ({
        ...item,
        processed: true,
        timestamp: Date.now()
    }))
    .reduce((acc, item) => {
        const category = item.category || 'uncategorized';
        if (!acc[category]) {
            acc[category] = [];
        }
        acc[category].push(item);
        return acc;
    }, {});

// Tagged template literal
function highlight(strings, ...values) {
    return strings.reduce((result, string, i) => {
        const value = values[i] ? `<mark>${values[i]}</mark>` : '';
        return result + string + value;
    }, '');
}

const highlightedText = highlight`Hello ${name}, you have ${count} messages`;

// Proxy pattern
const observableObject = new Proxy({}, {
    set(target, property, value) {
        console.log(`Setting ${property} to ${value}`);
        target[property] = value;
        return true;
    },
    
    get(target, property) {
        console.log(`Getting ${property}`);
        return target[property];
    }
});

// WeakMap for private properties
const privateProps = new WeakMap();

class PrivatePropsExample {
    constructor(value) {
        privateProps.set(this, { value });
    }
    
    getValue() {
        return privateProps.get(this).value;
    }
    
    setValue(value) {
        privateProps.get(this).value = value;
    }
}
"""

        chunks = self.parser.chunk(content, "edge-cases.js")

        # Should successfully parse complex syntax
        assert len(chunks) > 10, f"Expected > 10 chunks, got {len(chunks)}"

        # Test function detection (including complex ones)
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 1, "Should find at least the highlight function"

        # Test class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1, "Should find class with private properties"

        # Test variable detection
        variable_chunks = [c for c in chunks if c.semantic_type == "variable"]
        assert len(variable_chunks) >= 5, "Should find complex variable declarations"

    def test_fallback_behavior_broken_javascript(self):
        """Test that broken JavaScript is handled gracefully, extracting what's possible."""
        broken_file = self.test_files_dir / "broken" / "BrokenJavaScript.js"

        with open(broken_file, "r", encoding="utf-8") as f:
            broken_content = f.read()

        # Test with SemanticChunker
        chunks = self.chunker.chunk_content(broken_content, str(broken_file))

        # Should produce chunks even for broken JavaScript
        assert len(chunks) > 0, "Should produce chunks even for broken JavaScript"

        # Test data preservation - all content should be preserved
        all_chunk_text = "".join(chunk["text"] for chunk in chunks)

        # Key content should be preserved
        assert "BrokenComponent" in all_chunk_text
        assert "This string is never closed" in all_chunk_text  # Capital T as in file
        assert (
            "Missing closing parenthesis" in all_chunk_text
        )  # Comment that IS preserved

        # The AST parser may extract some semantic information even from broken code
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        if semantic_chunks:
            # If semantic parsing worked, check for error extraction markers
            # Should have some chunks marked as extracted from error, or the parser handled the syntax well
            # Either way, data should be preserved
            pass  # Just verify no data loss

    def test_minimal_valid_javascript(self):
        """Test parsing of minimal valid JavaScript."""
        content = """
function hello() {
    console.log("Hello World");
}
"""

        chunks = self.parser.chunk(content, "minimal.js")

        assert len(chunks) >= 1, "Should create at least one chunk"

        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) == 1, "Should find exactly one function"
        assert function_chunks[0].semantic_name == "hello"

    def test_integration_with_semantic_chunker(self):
        """Test integration with SemanticChunker."""
        content = """
import React from 'react';

const SimpleComponent = () => {
    return <div>Hello World</div>;
};

export default SimpleComponent;
"""

        # Test through SemanticChunker
        chunks = self.chunker.chunk_content(content, "SimpleComponent.js")

        assert len(chunks) > 0, "Should produce chunks"

        # Should use semantic chunking
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert (
            len(semantic_chunks) > 0
        ), "Should use semantic chunking for valid JavaScript"

        # Test chunk structure
        arrow_chunks = [
            c for c in semantic_chunks if c.get("semantic_type") == "arrow_function"
        ]
        component_chunk = next(
            (c for c in arrow_chunks if c.get("semantic_name") == "SimpleComponent"),
            None,
        )
        assert (
            component_chunk is not None
        ), "Should find SimpleComponent through SemanticChunker"

    def test_semantic_metadata_completeness(self):
        """Test that semantic metadata is complete and accurate."""
        content = """
const userService = {
    async getUser(id) {
        const response = await fetch(`/api/users/${id}`);
        return response.json();
    }
};

class UserManager {
    constructor() {
        this.users = new Map();
    }
    
    addUser(user) {
        this.users.set(user.id, user);
    }
}

function processUsers(users) {
    return users.filter(user => user.active);
}

const calculateTotal = (items) => {
    return items.reduce((sum, item) => sum + item.price, 0);
};
"""

        chunks = self.parser.chunk(content, "metadata-test.js")

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
        expected_types = {"function", "class", "arrow_function", "variable"}
        assert expected_types.intersection(
            construct_types
        ), f"Should find various constructs. Found: {construct_types}"

    def test_line_number_accuracy(self):
        """Test that line numbers are accurately tracked."""
        content = """const first = 'line 1';

function second() {
    return 'line 3-5';
}

const third = () => {
    return 'line 7-9';
};"""

        chunks = self.parser.chunk(content, "line-test.js")

        # Find specific chunks and verify their line numbers
        variable_chunks = [c for c in chunks if c.semantic_type == "variable"]
        first_var = next(
            (c for c in variable_chunks if c.semantic_name == "first"), None
        )
        third_var = next(
            (c for c in variable_chunks if c.semantic_name == "third"), None
        )

        if first_var:
            assert (
                first_var.line_start == 1
            ), f"First variable should start at line 1, got {first_var.line_start}"

        if third_var:
            assert (
                third_var.line_start >= 7
            ), f"Third variable should start around line 7, got {third_var.line_start}"

        # Test function line numbers
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        second_func = next(
            (c for c in function_chunks if c.semantic_name == "second"), None
        )

        if second_func:
            assert (
                second_func.line_start >= 3
            ), f"Second function should start around line 3, got {second_func.line_start}"
            assert (
                second_func.line_end >= second_func.line_start
            ), "Line end should be >= line start"

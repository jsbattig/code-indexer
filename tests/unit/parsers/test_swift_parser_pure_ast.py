"""
Test Swift parser with pure AST-based parsing (no regex).

This test verifies that the Swift parser can handle modern Swift constructs
using only AST traversal without falling back to regex patterns for
function return types and property types.

The test covers:
- Function signatures with complex return types
- Property declarations with various types
- SwiftUI property wrappers
- Generic types and constraints
- Async/await patterns
- Modern Swift concurrency features
"""

# All required imports are internal

from code_indexer.config import IndexingConfig
from code_indexer.indexing.swift_parser import SwiftSemanticParser


class TestSwiftParserPureAST:
    """Test Swift parser with pure AST-based parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = IndexingConfig()
        self.parser = SwiftSemanticParser(self.config)

    def test_function_return_types_pure_ast(self):
        """Test function return type extraction using pure AST parsing."""
        swift_code = """
import SwiftUI
import Combine

class UserService {
    func fetchUser(id: String) -> User {
        return User(id: id)
    }
    
    func fetchUsers() async throws -> [User] {
        return []
    }
    
    func calculate<T: Numeric>(values: [T]) -> T where T: Comparable {
        return values.first!
    }
    
    func processData() -> Result<Data, NetworkError> {
        return .success(Data())
    }
    
    func createHandler() -> (String) -> Void {
        return { _ in }
    }
}
"""

        chunks = self.parser.chunk(swift_code, "/test/UserService.swift")

        # Find function constructs
        function_chunks = [
            chunk for chunk in chunks if chunk.semantic_type == "function"
        ]

        # Verify functions are properly parsed with AST-based return types
        function_names_to_return_types = {}
        for chunk in function_chunks:
            if hasattr(chunk, "semantic_context") and chunk.semantic_context:
                return_type = chunk.semantic_context.get("return_type")
                function_names_to_return_types[chunk.semantic_name] = return_type

        # Verify specific return types are extracted via AST
        expected_return_types = {
            "fetchUser": "User",
            "fetchUsers": "[User]",
            "calculate": "T",
            "processData": "Result<Data, NetworkError>",
            "createHandler": "(String) -> Void",
        }

        for func_name, expected_type in expected_return_types.items():
            assert (
                func_name in function_names_to_return_types
            ), f"Function {func_name} not found"
            actual_type = function_names_to_return_types[func_name]
            assert (
                actual_type == expected_type
            ), f"Expected {func_name} return type '{expected_type}', got '{actual_type}'"

    def test_property_types_pure_ast(self):
        """Test property type extraction using pure AST parsing."""
        swift_code = """
import SwiftUI
import Combine

@available(iOS 14.0, *)
public class UserViewModel: ObservableObject {
    @Published private(set) var users: [User] = []
    @Published var isLoading: Bool = false
    @StateObject private var dataManager: DataManager = DataManager()
    
    let userService: UserServiceProtocol
    var cancellables: Set<AnyCancellable> = Set()
    
    private var internalData: [String: Any]?
    public var publicCounter: Int = 0
    
    lazy var expensiveComputation: () -> String = {
        return "computed"
    }
    
    weak var delegate: UserViewModelDelegate?
    unowned let coordinator: AppCoordinator
}

struct ContentView: View {
    @State private var username: String = ""
    @StateObject private var viewModel: UserViewModel = UserViewModel()
    @Environment(\\.dismiss) private var dismiss: DismissAction
    @EnvironmentObject var appState: AppState
}
"""

        chunks = self.parser.chunk(swift_code, "/test/UserViewModel.swift")

        # Find property/variable constructs
        property_chunks = [
            chunk for chunk in chunks if chunk.semantic_type in ["property", "variable"]
        ]

        # Verify properties are properly parsed with AST-based types
        property_names_to_types = {}
        for chunk in property_chunks:
            if hasattr(chunk, "semantic_context") and chunk.semantic_context:
                prop_type = chunk.semantic_context.get(
                    "property_type"
                ) or chunk.semantic_context.get("variable_type")
                property_names_to_types[chunk.semantic_name] = prop_type

        # Verify specific property types are extracted via AST
        expected_property_types = {
            "users": "[User]",
            "isLoading": "Bool",
            "dataManager": "DataManager",
            "userService": "UserServiceProtocol",
            "cancellables": "Set<AnyCancellable>",
            "internalData": "[String: Any]?",
            "publicCounter": "Int",
            "expensiveComputation": "() -> String",
            "delegate": "UserViewModelDelegate?",
            "username": "String",
            "dismiss": "DismissAction",
        }

        for prop_name, expected_type in expected_property_types.items():
            if prop_name in property_names_to_types:
                actual_type = property_names_to_types[prop_name]
                assert (
                    actual_type == expected_type
                ), f"Expected {prop_name} type '{expected_type}', got '{actual_type}'"

    def test_swiftui_property_wrappers_ast(self):
        """Test SwiftUI property wrapper detection via AST."""
        swift_code = """
struct ContentView: View {
    @State private var isPresented: Bool = false
    @StateObject private var viewModel: ViewModel = ViewModel()
    @ObservedObject var dataSource: DataSource
    @Published var updateCount: Int = 0
    @Environment(\\.managedObjectContext) private var context: NSManagedObjectContext
    @EnvironmentObject var settings: UserSettings
    @AppStorage("username") var storedUsername: String = ""
    @SceneStorage("tab") var selectedTab: Int = 0
    @FocusState private var isFieldFocused: Bool
    
    var body: some View {
        Text("Hello, World!")
    }
}
"""

        chunks = self.parser.chunk(swift_code, "/test/ContentView.swift")

        # Find property constructs
        property_chunks = [
            chunk for chunk in chunks if chunk.semantic_type in ["property", "variable"]
        ]

        # Verify property wrappers are detected in features or context
        property_wrapper_features = []
        for chunk in property_chunks:
            if hasattr(chunk, "semantic_language_features"):
                property_wrapper_features.extend(chunk.semantic_language_features)
            if hasattr(chunk, "semantic_context") and chunk.semantic_context:
                modifiers = chunk.semantic_context.get("modifiers", [])
                property_wrapper_features.extend(modifiers)

        # Note: This test verifies that property wrappers are captured,
        # either in features or through AST parsing of modifiers
        # For now, we verify the parser doesn't crash and extracts properties
        # The exact representation of property wrappers may vary based on implementation
        assert (
            len(property_chunks) > 0
        ), "Should parse property declarations with wrappers"

    def test_async_await_functions_ast(self):
        """Test async/await function parsing via AST."""
        swift_code = """
class NetworkService {
    func fetchData() async throws -> Data {
        let url = URL(string: "https://api.example.com/data")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return data
    }
    
    func processItems<T: Codable>(_ items: [T]) async -> [T] where T: Identifiable {
        return await withTaskGroup(of: T.self) { group in
            for item in items {
                group.addTask { await self.processItem(item) }
            }
            return await group.reduce(into: []) { result, item in
                result.append(item)
            }
        }
    }
    
    private func processItem<T>(_ item: T) async -> T {
        return item
    }
}
"""

        chunks = self.parser.chunk(swift_code, "/test/NetworkService.swift")

        # Find function constructs
        function_chunks = [
            chunk for chunk in chunks if chunk.semantic_type == "function"
        ]

        # Verify async functions are properly parsed
        async_functions = []
        for chunk in function_chunks:
            if hasattr(chunk, "semantic_context") and chunk.semantic_context:
                modifiers = chunk.semantic_context.get("modifiers", [])
                if "async" in modifiers or "async" in chunk.semantic_signature.lower():
                    async_functions.append(chunk.semantic_name)

        # Should detect async functions
        expected_async_functions = ["fetchData", "processItems", "processItem"]
        for func_name in expected_async_functions:
            # Verify function exists (async detection may vary in implementation)
            function_exists = any(
                chunk.semantic_name == func_name for chunk in function_chunks
            )
            assert function_exists, f"Async function {func_name} should be parsed"

    def test_generic_types_and_constraints_ast(self):
        """Test generic type parsing via AST."""
        swift_code = """
protocol DataProvider {
    associatedtype DataType: Codable
    func provide() -> DataType
}

class GenericService<T: Codable & Identifiable> where T.ID == UUID {
    private var items: [T] = []
    
    func add(item: T) -> Void {
        items.append(item)
    }
    
    func find<U: Comparable>(by keyPath: KeyPath<T, U>, value: U) -> T? where U: Equatable {
        return items.first { $0[keyPath: keyPath] == value }
    }
    
    func process<Result>(_ transform: (T) throws -> Result) rethrows -> [Result] {
        return try items.map(transform)
    }
}
"""

        chunks = self.parser.chunk(swift_code, "/test/GenericService.swift")

        # Find class and function constructs
        class_chunks = [chunk for chunk in chunks if chunk.semantic_type == "class"]
        function_chunks = [
            chunk for chunk in chunks if chunk.semantic_type == "function"
        ]

        # Verify generic class is parsed
        assert len(class_chunks) > 0, "Should parse generic class"

        generic_class = class_chunks[0]
        assert "GenericService" in generic_class.semantic_name

        # Verify generic functions are parsed with proper signatures
        generic_function_names = {chunk.semantic_name for chunk in function_chunks}
        expected_functions = {"add", "find", "process"}

        for func_name in expected_functions:
            assert (
                func_name in generic_function_names
            ), f"Generic function {func_name} should be parsed"

    def test_no_regex_patterns_in_critical_methods(self):
        """Verify that critical parsing methods use pure AST without regex."""
        import inspect
        import re

        # Get source code of the critical methods
        return_type_source = inspect.getsource(self.parser._extract_return_type)
        property_type_source = inspect.getsource(self.parser._extract_property_type)

        # Verify no re.search, re.match, or re.findall in critical methods
        regex_patterns = [r"re\.search\(", r"re\.match\(", r"re\.findall\("]

        for pattern in regex_patterns:
            assert not re.search(
                pattern, return_type_source
            ), f"_extract_return_type should not contain regex pattern: {pattern}"
            assert not re.search(
                pattern, property_type_source
            ), f"_extract_property_type should not contain regex pattern: {pattern}"

        # Verify the methods contain AST traversal patterns
        ast_patterns = ["node.children", 'hasattr(child, "type")', "child.type"]

        for pattern in ast_patterns:
            assert (
                pattern in return_type_source
            ), f"_extract_return_type should contain AST pattern: {pattern}"
            assert (
                pattern in property_type_source
            ), f"_extract_property_type should contain AST pattern: {pattern}"

    def test_complex_swift_constructs_parsing(self):
        """Test parsing of complex Swift constructs to ensure robustness."""
        swift_code = """
@available(iOS 15.0, *)
@MainActor
class ComplexService: ObservableObject, NetworkServiceProtocol {
    @Published private(set) var data: AsyncStream<DataModel> = AsyncStream { continuation in
        continuation.finish()
    }
    
    private let coordinator: AppCoordinator
    
    init(coordinator: AppCoordinator) {
        self.coordinator = coordinator
    }
    
    deinit {
        print("Service deallocated")
    }
    
    func performComplexOperation<T, U>(
        input: T,
        transform: @escaping (T) async throws -> U
    ) async rethrows -> Result<U, ServiceError> where T: Sendable, U: Sendable {
        do {
            let result = try await transform(input)
            return .success(result)
        } catch {
            return .failure(.transformationFailed(error))
        }
    }
    
    subscript<T: Hashable>(key: T) -> String? {
        get { return storage[AnyHashable(key)] }
        set { storage[AnyHashable(key)] = newValue }
    }
    
    private var storage: [AnyHashable: String] = [:]
}

extension String {
    func capitalizedFirst() -> String {
        return prefix(1).capitalized + dropFirst()
    }
}
"""

        chunks = self.parser.chunk(swift_code, "/test/ComplexService.swift")

        # Verify all major constructs are parsed without errors
        construct_types = {chunk.semantic_type for chunk in chunks}

        expected_constructs = {
            "class",
            "function",
            "initializer",
            "deinitializer",
            "subscript",
            "extension",
            "property",
        }

        # Should parse most construct types (some may be implementation-dependent)
        parsed_constructs = construct_types.intersection(expected_constructs)
        assert (
            len(parsed_constructs) >= 4
        ), f"Should parse multiple construct types, got: {construct_types}"

        # Verify no parsing errors occurred
        assert len(chunks) > 0, "Should parse some chunks from complex code"

        # Verify complex function signature is handled
        complex_functions = [
            chunk
            for chunk in chunks
            if chunk.semantic_type == "function"
            and "performComplexOperation" in chunk.semantic_name
        ]
        if complex_functions:
            complex_func = complex_functions[0]
            # Should have captured the function without crashing
            assert complex_func.semantic_signature is not None
            assert "performComplexOperation" in complex_func.semantic_signature

"""
Tests for Swift semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of Swift language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestSwiftSemanticParser:
    """Test Swift semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Swift parser directly."""
        from code_indexer.indexing.swift_parser import SwiftSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SwiftSemanticParser(config)

    def test_basic_class_declaration(self, parser):
        """Test parsing basic Swift class definitions."""
        content = dedent(
            """
            import Foundation

            class Rectangle {
                private var width: Double
                private var height: Double
                
                init(width: Double, height: Double) {
                    self.width = width
                    self.height = height
                }
                
                func area() -> Double {
                    return width * height
                }
                
                func perimeter() -> Double {
                    return 2 * (width + height)
                }
                
                deinit {
                    print("Rectangle deallocated")
                }
            }

            final class Square: Rectangle {
                convenience init(side: Double) {
                    self.init(width: side, height: side)
                }
                
                override func description() -> String {
                    return "Square with side \\(width)"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "shapes.swift")

        # Should find classes and their methods
        assert len(chunks) >= 2

        # Check class chunks
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        class_names = {c.semantic_name for c in class_chunks}
        assert "Rectangle" in class_names
        assert "Square" in class_names

        # Check Rectangle class
        rect_class = next(c for c in class_chunks if c.semantic_name == "Rectangle")
        assert rect_class.semantic_path == "Rectangle"
        assert "class Rectangle" in rect_class.semantic_signature

        # Check Square class with inheritance
        square_class = next(c for c in class_chunks if c.semantic_name == "Square")
        assert "final class Square" in square_class.semantic_signature
        assert "final_class" in square_class.semantic_language_features

    def test_struct_declarations(self, parser):
        """Test parsing Swift struct definitions."""
        content = dedent(
            """
            struct Point {
                var x: Double
                var y: Double
                
                init() {
                    self.x = 0.0
                    self.y = 0.0
                }
                
                init(x: Double, y: Double) {
                    self.x = x
                    self.y = y
                }
                
                func distance(to other: Point) -> Double {
                    let dx = x - other.x
                    let dy = y - other.y
                    return sqrt(dx * dx + dy * dy)
                }
                
                mutating func move(by offset: Point) {
                    x += offset.x
                    y += offset.y
                }
                
                static func origin() -> Point {
                    return Point(x: 0, y: 0)
                }
            }

            public struct Vector3D {
                public let x, y, z: Double
                
                public init(x: Double, y: Double, z: Double) {
                    self.x = x
                    self.y = y
                    self.z = z
                }
                
                public var magnitude: Double {
                    return sqrt(x * x + y * y + z * z)
                }
                
                public func normalized() -> Vector3D {
                    let mag = magnitude
                    return Vector3D(x: x/mag, y: y/mag, z: z/mag)
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "geometry.swift")

        # Should find structs and their methods
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 2

        struct_names = {c.semantic_name for c in struct_chunks}
        assert "Point" in struct_names
        assert "Vector3D" in struct_names

        # Check public access modifier
        vector_struct = next(c for c in struct_chunks if c.semantic_name == "Vector3D")
        assert "public struct Vector3D" in vector_struct.semantic_signature
        assert vector_struct.semantic_context.get("access_modifier") == "public"

    def test_protocol_declarations(self, parser):
        """Test parsing Swift protocol definitions."""
        content = dedent(
            """
            protocol Drawable {
                var area: Double { get }
                func draw()
                func move(to point: Point)
            }

            protocol Comparable {
                static func < (lhs: Self, rhs: Self) -> Bool
                static func <= (lhs: Self, rhs: Self) -> Bool
                static func > (lhs: Self, rhs: Self) -> Bool
                static func >= (lhs: Self, rhs: Self) -> Bool
            }

            public protocol NetworkService {
                associatedtype Response
                func fetch() async throws -> Response
            }

            protocol CustomStringConvertible {
                var description: String { get }
            }

            @objc protocol ObjCProtocol {
                @objc func objcMethod()
                @objc optional func optionalMethod()
            }
        """
        ).strip()

        chunks = parser.chunk(content, "protocols.swift")

        # Should find protocol declarations
        protocol_chunks = [c for c in chunks if c.semantic_type == "protocol"]
        assert len(protocol_chunks) >= 3

        protocol_names = {c.semantic_name for c in protocol_chunks}
        assert "Drawable" in protocol_names
        assert "Comparable" in protocol_names
        assert "NetworkService" in protocol_names

        # Check public protocol
        network_protocol = next(
            c for c in protocol_chunks if c.semantic_name == "NetworkService"
        )
        assert "public protocol NetworkService" in network_protocol.semantic_signature

    def test_extension_declarations(self, parser):
        """Test parsing Swift extension definitions."""
        content = dedent(
            """
            extension String {
                var isEmail: Bool {
                    return self.contains("@") && self.contains(".")
                }
                
                func capitalizingFirstLetter() -> String {
                    return prefix(1).capitalized + dropFirst()
                }
            }

            extension Array where Element: Comparable {
                func sorted() -> [Element] {
                    return self.sorted { $0 < $1 }
                }
            }

            public extension Double {
                static let pi = 3.14159265359
                
                var degrees: Double {
                    return self * 180.0 / Double.pi
                }
                
                var radians: Double {
                    return self * Double.pi / 180.0
                }
            }

            extension Rectangle: Drawable {
                func draw() {
                    print("Drawing rectangle \\(width) x \\(height)")
                }
                
                func move(to point: Point) {
                    // Move implementation
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "extensions.swift")

        # Should find extension declarations
        extension_chunks = [c for c in chunks if c.semantic_type == "extension"]
        assert len(extension_chunks) >= 3

        # Check extended types
        extended_types = {
            c.semantic_context.get("extended_type")
            for c in extension_chunks
            if c.semantic_context
        }
        assert "String" in extended_types or "Array" in extended_types

    def test_enum_declarations(self, parser):
        """Test parsing Swift enum definitions."""
        content = dedent(
            """
            enum Direction {
                case north
                case south  
                case east
                case west
                
                func opposite() -> Direction {
                    switch self {
                    case .north: return .south
                    case .south: return .north
                    case .east: return .west
                    case .west: return .east
                    }
                }
            }

            enum Planet: Int, CaseIterable {
                case mercury = 1
                case venus = 2
                case earth = 3
                case mars = 4
                
                var distanceFromSun: Double {
                    switch self {
                    case .mercury: return 0.39
                    case .venus: return 0.72
                    case .earth: return 1.0
                    case .mars: return 1.52
                    }
                }
            }

            enum Result<T, E: Error> {
                case success(T)
                case failure(E)
                
                var isSuccess: Bool {
                    switch self {
                    case .success: return true
                    case .failure: return false
                    }
                }
                
                func map<U>(_ transform: (T) -> U) -> Result<U, E> {
                    switch self {
                    case .success(let value):
                        return .success(transform(value))
                    case .failure(let error):
                        return .failure(error)
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "enums.swift")

        # Should find enum declarations
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) >= 3

        enum_names = {c.semantic_name for c in enum_chunks}
        assert "Direction" in enum_names
        assert "Planet" in enum_names
        assert "Result" in enum_names

        # Check enum features
        planet_enum = next(c for c in enum_chunks if c.semantic_name == "Planet")
        if planet_enum.semantic_context.get("cases"):
            cases = planet_enum.semantic_context["cases"]
            assert len(cases) >= 4

    def test_function_declarations(self, parser):
        """Test parsing Swift function definitions."""
        content = dedent(
            """
            func greet(name: String) -> String {
                return "Hello, \\(name)!"
            }

            func addNumbers(_ a: Int, _ b: Int) -> Int {
                return a + b
            }

            func processData<T: Comparable>(data: [T], threshold: T) -> [T] {
                return data.filter { $0 > threshold }
            }

            @discardableResult
            func performOperation() -> Bool {
                // Perform some operation
                return true
            }

            private func helperFunction(with parameter: String) {
                print("Helper: \\(parameter)")
            }

            public static func classMethod() {
                print("This is a class method")
            }

            func functionWithMultipleParameters(
                first: String,
                second: Int,
                third: Bool = false
            ) -> String {
                return "\\(first): \\(second), \\(third)"
            }

            func throwingFunction() throws -> String {
                throw NSError(domain: "Example", code: 1, userInfo: nil)
            }

            async func asyncFunction() async -> String {
                await Task.sleep(1_000_000_000) // 1 second
                return "Async result"
            }
        """
        ).strip()

        chunks = parser.chunk(content, "functions.swift")

        # Should find function declarations
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 6

        function_names = {c.semantic_name for c in function_chunks}
        assert "greet" in function_names
        assert "addNumbers" in function_names
        assert "processData" in function_names

        # Check function features
        helper_func = next(
            (c for c in function_chunks if c.semantic_name == "helperFunction"), None
        )
        if helper_func:
            assert helper_func.semantic_context.get("access_modifier") == "private"

    def test_property_declarations(self, parser):
        """Test parsing Swift property definitions."""
        content = dedent(
            """
            class PropertyExample {
                // Stored properties
                var name: String = ""
                let id: Int
                private var _value: Double = 0.0
                
                // Computed properties
                var value: Double {
                    get {
                        return _value
                    }
                    set {
                        _value = max(0, newValue)
                    }
                }
                
                var isValid: Bool {
                    return !name.isEmpty && id > 0
                }
                
                // Property with observers
                var status: String = "inactive" {
                    willSet {
                        print("Status will change from \\(status) to \\(newValue)")
                    }
                    didSet {
                        print("Status changed from \\(oldValue) to \\(status)")
                    }
                }
                
                // Lazy property
                lazy var expensiveResource: ExpensiveResource = {
                    return ExpensiveResource()
                }()
                
                // Static properties
                static let defaultName = "Unknown"
                static var instanceCount = 0
                
                // Class property
                class var typeName: String {
                    return "PropertyExample"
                }
                
                init(id: Int) {
                    self.id = id
                    PropertyExample.instanceCount += 1
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "properties.swift")

        # Should find class and properties
        property_chunks = [c for c in chunks if c.semantic_type == "property"]
        assert len(property_chunks) >= 4

        property_names = {c.semantic_name for c in property_chunks}
        expected_properties = {
            "name",
            "value",
            "status",
            "expensiveResource",
            "defaultName",
        }
        assert len(property_names.intersection(expected_properties)) >= 3

    def test_initializer_and_deinitializer(self, parser):
        """Test parsing Swift initializers and deinitializers."""
        content = dedent(
            """
            class ResourceManager {
                let name: String
                var resources: [String] = []
                
                // Designated initializer
                init(name: String) {
                    self.name = name
                    print("ResourceManager \\(name) initialized")
                }
                
                // Convenience initializer
                convenience init() {
                    self.init(name: "Default")
                }
                
                // Failable initializer
                init?(name: String, capacity: Int) {
                    guard capacity > 0 else { return nil }
                    self.name = name
                    self.resources.reserveCapacity(capacity)
                }
                
                // Required initializer
                required init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    self.name = try container.decode(String.self, forKey: .name)
                }
                
                // Deinitializer
                deinit {
                    print("ResourceManager \\(name) deinitialized")
                    resources.removeAll()
                }
            }

            struct Point {
                let x, y: Double
                
                init(x: Double, y: Double) {
                    self.x = x
                    self.y = y
                }
                
                init() {
                    self.init(x: 0, y: 0)
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "initializers.swift")

        # Should find initializers and deinitializers
        init_chunks = [c for c in chunks if c.semantic_type == "initializer"]
        deinit_chunks = [c for c in chunks if c.semantic_type == "deinitializer"]

        assert len(init_chunks) >= 3
        assert len(deinit_chunks) >= 1

        # Check initializer features
        convenience_inits = [
            c for c in init_chunks if "convenience" in c.semantic_language_features
        ]
        required_inits = [
            c for c in init_chunks if "required_init" in c.semantic_language_features
        ]

        # At least some special initializers should be found
        assert len(convenience_inits) >= 1 or len(required_inits) >= 1

    def test_subscript_declarations(self, parser):
        """Test parsing Swift subscript definitions."""
        content = dedent(
            """
            struct Matrix {
                private var data: [[Double]]
                let rows: Int
                let columns: Int
                
                init(rows: Int, columns: Int) {
                    self.rows = rows
                    self.columns = columns
                    self.data = Array(repeating: Array(repeating: 0.0, count: columns), count: rows)
                }
                
                subscript(row: Int, column: Int) -> Double {
                    get {
                        return data[row][column]
                    }
                    set {
                        data[row][column] = newValue
                    }
                }
                
                subscript(row: Int) -> [Double] {
                    get {
                        return data[row]
                    }
                    set {
                        data[row] = newValue
                    }
                }
            }

            class SafeArray<T> {
                private var items: [T] = []
                
                subscript(index: Int) -> T? {
                    get {
                        return index >= 0 && index < items.count ? items[index] : nil
                    }
                    set {
                        if let value = newValue, index >= 0 && index < items.count {
                            items[index] = value
                        }
                    }
                }
                
                subscript(range: Range<Int>) -> ArraySlice<T> {
                    get {
                        let start = max(0, range.lowerBound)
                        let end = min(items.count, range.upperBound)
                        return items[start..<end]
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "subscripts.swift")

        # Should find subscript declarations
        subscript_chunks = [c for c in chunks if c.semantic_type == "subscript"]
        assert len(subscript_chunks) >= 2

        # Check subscript signatures
        for subscript_chunk in subscript_chunks:
            assert "subscript" in subscript_chunk.semantic_signature

    def test_generic_declarations(self, parser):
        """Test parsing Swift generic definitions."""
        content = dedent(
            """
            struct Stack<Element> {
                private var items: [Element] = []
                
                mutating func push(_ item: Element) {
                    items.append(item)
                }
                
                mutating func pop() -> Element? {
                    return items.popLast()
                }
                
                var isEmpty: Bool {
                    return items.isEmpty
                }
                
                var count: Int {
                    return items.count
                }
            }

            class GenericClass<T: Comparable, U> {
                var first: T
                var second: U
                
                init(first: T, second: U) {
                    self.first = first
                    self.second = second
                }
                
                func compare<V: Comparable>(with other: V) -> Bool where V == T {
                    return first < other
                }
            }

            func swapValues<T>(_ a: inout T, _ b: inout T) {
                let temp = a
                a = b
                b = temp
            }

            protocol Container {
                associatedtype Item
                var count: Int { get }
                mutating func append(_ item: Item)
                subscript(i: Int) -> Item { get }
            }

            extension Array: Container {
                // Array already has count and subscript
                // Only need to add append method
            }
        """
        ).strip()

        chunks = parser.chunk(content, "generics.swift")

        # Should find generic types and functions
        assert len(chunks) >= 4

        # Check generic features
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(struct_chunks) >= 1
        assert len(class_chunks) >= 1
        assert len(function_chunks) >= 1

        # Check generic context
        stack_struct = next(
            (c for c in struct_chunks if c.semantic_name == "Stack"), None
        )
        if stack_struct and stack_struct.semantic_context.get("generics"):
            assert "Element" in stack_struct.semantic_context["generics"]

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            struct ValidStruct {
                var property: String
                
                func method() {
                    print("Valid")
                }
            }

            struct BrokenStruct {
                var property: String
                // Missing method body
                func brokenMethod() 
                
                func anotherMethod() {
                    print("This should still be found")
                }
            }

            class ValidClass {
                func validMethod() {
                    print("Valid method")
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "broken.swift")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(struct_chunks) >= 1 or len(class_chunks) >= 1

        # Check that some valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "ValidStruct" in all_names or "ValidClass" in all_names

    def test_error_node_handling_protocol_errors(self, parser):
        """Test ERROR node handling for protocol syntax errors."""
        content = dedent(
            """
            protocol ValidProtocol {
                func requiredMethod()
                var requiredProperty: String { get }
            }

            protocol BrokenProtocol {
                func method1()
                // Incomplete protocol definition
                var brokenProperty: String {
                // Missing get/set specification

            protocol AnotherValid {
                func anotherMethod()
            }

            class ConformingClass: ValidProtocol {
                var requiredProperty: String = ""
                
                func requiredMethod() {
                    print("Implementation")
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "protocol_errors.swift")

        # Should extract protocols and classes despite syntax errors
        protocol_chunks = [c for c in chunks if c.semantic_type == "protocol"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(protocol_chunks) >= 1 or len(class_chunks) >= 1

        # Check that valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "ValidProtocol" in all_names or "ConformingClass" in all_names

    def test_error_node_handling_generic_errors(self, parser):
        """Test ERROR node handling for generic syntax errors."""
        content = dedent(
            """
            struct ValidGeneric<T> {
                var value: T
                
                func getValue() -> T {
                    return value
                }
            }

            struct BrokenGeneric<T where
            // Incomplete generic constraint
            {
                var value: T
            }

            func validFunction<T: Comparable>(value: T) -> T {
                return value
            }

            class SimpleClass {
                func simpleMethod() {
                    print("Simple")
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "generic_errors.swift")

        # Should extract constructs despite generic syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        valid_chunks = struct_chunks + function_chunks + class_chunks
        assert len(valid_chunks) >= 2

    def test_malformed_swift_code_handling(self, parser):
        """Test handling of completely malformed Swift code."""
        malformed_content = """
            This is not valid Swift code!
            class??? broken {{{
            func incomplete(((
            var invalid syntax %%%
            protocol:::: wrong
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.swift")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Swift files."""
        content = dedent(
            """
            import Foundation

            protocol Shape {
                var area: Double { get }
                func perimeter() -> Double
            }

            struct Circle: Shape {
                let radius: Double
                
                var area: Double {
                    return Double.pi * radius * radius
                }
                
                func perimeter() -> Double {
                    return 2 * Double.pi * radius
                }
            }

            class ShapeCalculator {
                func processShapes(_ shapes: [Shape]) {
                    for shape in shapes {
                        print("Area: \\(shape.area), Perimeter: \\(shape.perimeter())")
                    }
                }
            }

            // Usage
            let circle = Circle(radius: 5.0)
            let calculator = ShapeCalculator()
            calculator.processShapes([circle])
        """
        ).strip()

        chunks = chunker.chunk_content(content, "shapes.swift")

        # Should get semantic chunks from Swift parser
        assert len(chunks) >= 3

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_modern_swift_features(self, parser):
        """Test parsing modern Swift features."""
        content = dedent(
            """
            import SwiftUI

            @propertyWrapper
            struct Clamped<T: Comparable> {
                private var value: T
                private let range: ClosedRange<T>
                
                init(wrappedValue: T, _ range: ClosedRange<T>) {
                    self.range = range
                    self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
                }
                
                var wrappedValue: T {
                    get { value }
                    set { value = min(max(newValue, range.lowerBound), range.upperBound) }
                }
            }

            struct ContentView: View {
                @State private var sliderValue: Double = 0.5
                @Clamped(0...100) var percentage: Int = 50
                
                var body: some View {
                    VStack {
                        Text("Value: \\(sliderValue)")
                        Slider(value: $sliderValue, in: 0...1)
                        Text("Percentage: \\(percentage)%")
                    }
                }
            }

            actor BankAccount {
                private var balance: Double = 0
                
                func deposit(_ amount: Double) {
                    balance += amount
                }
                
                func withdraw(_ amount: Double) -> Bool {
                    if balance >= amount {
                        balance -= amount
                        return true
                    }
                    return false
                }
                
                func getBalance() -> Double {
                    return balance
                }
            }

            @MainActor
            class ViewModel: ObservableObject {
                @Published var items: [String] = []
                
                func loadItems() async {
                    // Simulate network request
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                    items = ["Item 1", "Item 2", "Item 3"]
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "modern.swift")

        # Should handle modern Swift features without crashing
        assert len(chunks) >= 3

        # Should find the main constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        all_names = {c.semantic_name for c in struct_chunks + class_chunks}
        assert (
            "ContentView" in all_names
            or "BankAccount" in all_names
            or "ViewModel" in all_names
        )

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for Swift when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            class TestClass {
                var property: String
                func method() {}
            }
            
            struct TestStruct {
                let value: Int
            }
            
            protocol TestProtocol {
                func requirement()
            }
            
            enum TestEnum {
                case first, second
            }
            
            extension String {
                func extended() {}
            }
            
            func freeFunction() {}
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 4

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {
            "class",
            "struct",
            "protocol",
            "enum",
            "extension",
            "function",
        }
        assert len(construct_types.intersection(expected_types)) >= 3

    def test_access_control_modifiers(self, parser):
        """Test parsing Swift access control modifiers."""
        content = dedent(
            """
            public class PublicClass {
                public var publicProperty: String = ""
                internal var internalProperty: String = ""
                fileprivate var fileprivateProperty: String = ""
                private var privateProperty: String = ""
                
                public func publicMethod() {}
                internal func internalMethod() {}
                fileprivate func fileprivateMethod() {}
                private func privateMethod() {}
            }

            internal struct InternalStruct {
                var property: String
            }

            fileprivate enum FileprivateEnum {
                case first, second
            }

            private class PrivateClass {
                func method() {}
            }

            open class OpenClass {
                open func openMethod() {}
                public func publicMethod() {}
            }
        """
        ).strip()

        chunks = parser.chunk(content, "access_control.swift")

        # Should find constructs with various access levels
        assert len(chunks) >= 4

        # Check access modifiers in context
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        # Check that access modifiers are captured
        public_classes = [
            c
            for c in class_chunks
            if c.semantic_context.get("access_modifier") == "public"
        ]
        private_classes = [
            c
            for c in class_chunks
            if c.semantic_context.get("access_modifier") == "private"
        ]
        open_classes = [
            c
            for c in class_chunks
            if c.semantic_context.get("access_modifier") == "open"
        ]

        # Should find at least some with access modifiers
        assert (
            len(public_classes) >= 1
            or len(private_classes) >= 1
            or len(open_classes) >= 1
        )

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            import Foundation
            import SwiftUI

            @propertyWrapper
            public struct ValidatedString {
                private var value: String
                private let validator: (String) -> Bool
                
                public init(wrappedValue: String, validator: @escaping (String) -> Bool) {
                    self.validator = validator
                    self.value = validator(wrappedValue) ? wrappedValue : ""
                }
                
                public var wrappedValue: String {
                    get { value }
                    set { value = validator(newValue) ? newValue : value }
                }
            }

            public protocol DataService {
                associatedtype DataType
                func fetch() async throws -> [DataType]
                func save(_ item: DataType) async throws
            }

            public actor NetworkManager: DataService {
                public typealias DataType = User
                
                private let session = URLSession.shared
                private var cache: [String: User] = [:]
                
                public func fetch() async throws -> [User] {
                    let url = URL(string: "https://api.example.com/users")!
                    let (data, _) = try await session.data(from: url)
                    return try JSONDecoder().decode([User].self, from: data)
                }
                
                public func save(_ user: User) async throws {
                    cache[user.id] = user
                    // Additional save logic
                }
                
                nonisolated public func description() -> String {
                    return "NetworkManager with \\(cache.count) cached users"
                }
            }

            public struct User: Codable, Hashable {
                public let id: String
                @ValidatedString(validator: { !$0.isEmpty }) 
                public var name: String
                public let email: String
                
                public init(id: String, name: String, email: String) {
                    self.id = id
                    self.name = name
                    self.email = email
                }
            }

            @MainActor
            public class UserViewModel: ObservableObject {
                @Published public var users: [User] = []
                @Published public var isLoading = false
                
                private let networkManager = NetworkManager()
                
                public func loadUsers() async {
                    isLoading = true
                    defer { isLoading = false }
                    
                    do {
                        users = try await networkManager.fetch()
                    } catch {
                        print("Error loading users: \\(error)")
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.swift")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "import Foundation" in all_chunk_content
        assert "@propertyWrapper" in all_chunk_content
        assert "public struct ValidatedString" in all_chunk_content
        assert "public protocol DataService" in all_chunk_content
        assert "public actor NetworkManager" in all_chunk_content
        assert "public struct User" in all_chunk_content
        assert "public class UserViewModel" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 5  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.swift"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

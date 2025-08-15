"""
Tests for Pascal/Delphi semantic parser using tree-sitter.
Following TDD approach - writing comprehensive tests first.

Tests cover Pascal/Delphi language constructs:
- Units/Programs
- Classes/Objects
- Procedures/Functions
- Properties
- Interfaces
- Records/Types
- Constants/Variables
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestPascalSemanticParser:
    """Test Pascal/Delphi semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Pascal parser directly."""
        from code_indexer.indexing.pascal_parser import PascalSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return PascalSemanticParser(config)

    def test_unit_declaration_chunking(self, parser):
        """Test parsing Pascal unit declarations."""
        content = dedent(
            """
            unit Calculator;
            
            interface
            
            type
              TCalculator = class
              private
                FValue: Integer;
              public
                constructor Create(AValue: Integer);
                function Add(ANumber: Integer): Integer;
                property Value: Integer read FValue write FValue;
              end;
              
            implementation
            
            constructor TCalculator.Create(AValue: Integer);
            begin
              FValue := AValue;
            end;
            
            function TCalculator.Add(ANumber: Integer): Integer;
            begin
              Result := FValue + ANumber;
            end;
            
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "Calculator.pas")

        # Should find: unit, class, constructor, function, property
        assert len(chunks) >= 5

        # Check unit chunk
        unit_chunk = next((c for c in chunks if c.semantic_type == "unit"), None)
        assert unit_chunk is not None
        assert unit_chunk.semantic_name == "Calculator"
        assert unit_chunk.semantic_path == "Calculator"
        assert unit_chunk.line_start == 1

        # Check class chunk
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "TCalculator"
        assert class_chunk.semantic_path == "Calculator.TCalculator"
        assert class_chunk.semantic_parent == "Calculator"

        # Check constructor
        constructor_chunk = next(
            (c for c in chunks if c.semantic_type == "constructor"), None
        )
        assert constructor_chunk is not None
        assert constructor_chunk.semantic_name == "Create"
        assert constructor_chunk.semantic_path == "Calculator.TCalculator.Create"
        assert constructor_chunk.semantic_parent == "TCalculator"
        assert "AValue: Integer" in constructor_chunk.semantic_signature

        # Check function
        function_chunk = next(
            (
                c
                for c in chunks
                if c.semantic_type == "function" and c.semantic_name == "Add"
            ),
            None,
        )
        assert function_chunk is not None
        assert function_chunk.semantic_path == "Calculator.TCalculator.Add"
        assert function_chunk.semantic_parent == "TCalculator"
        assert "Integer" in function_chunk.semantic_signature

        # Check property
        property_chunk = next(
            (c for c in chunks if c.semantic_type == "property"), None
        )
        assert property_chunk is not None
        assert property_chunk.semantic_name == "Value"
        assert property_chunk.semantic_path == "Calculator.TCalculator.Value"
        assert property_chunk.semantic_parent == "TCalculator"

    def test_program_declaration_chunking(self, parser):
        """Test parsing Pascal program declarations."""
        content = dedent(
            """
            program HelloWorld;
            
            procedure SayHello;
            begin
              WriteLn('Hello, World!');
            end;
            
            function GetGreeting: string;
            begin
              Result := 'Hello from Pascal!';
            end;
            
            begin
              SayHello;
              WriteLn(GetGreeting);
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "HelloWorld.dpr")

        # Should find: program, procedure, function
        assert len(chunks) >= 3

        # Check program chunk
        program_chunk = next((c for c in chunks if c.semantic_type == "program"), None)
        assert program_chunk is not None
        assert program_chunk.semantic_name == "HelloWorld"
        assert program_chunk.semantic_path == "HelloWorld"

        # Check procedure
        procedure_chunk = next(
            (c for c in chunks if c.semantic_type == "procedure"), None
        )
        assert procedure_chunk is not None
        assert procedure_chunk.semantic_name == "SayHello"
        assert procedure_chunk.semantic_path == "HelloWorld.SayHello"
        assert procedure_chunk.semantic_parent == "HelloWorld"

        # Check function
        function_chunk = next(
            (c for c in chunks if c.semantic_type == "function"), None
        )
        assert function_chunk is not None
        assert function_chunk.semantic_name == "GetGreeting"
        assert function_chunk.semantic_path == "HelloWorld.GetGreeting"
        assert function_chunk.semantic_parent == "HelloWorld"
        assert "string" in function_chunk.semantic_signature

    def test_interface_implementation_chunking(self, parser):
        """Test parsing interface declarations."""
        content = dedent(
            """
            unit Interfaces;
            
            interface
            
            type
              ICalculator = interface
                ['{12345678-1234-1234-1234-123456789012}']
                function Add(A, B: Integer): Integer;
                function Subtract(A, B: Integer): Integer;
                property Value: Integer read GetValue write SetValue;
              end;
              
              TCalculatorImpl = class(TInterfacedObject, ICalculator)
              private
                FValue: Integer;
                function GetValue: Integer;
                procedure SetValue(const Value: Integer);
              public
                function Add(A, B: Integer): Integer;
                function Subtract(A, B: Integer): Integer;
                property Value: Integer read GetValue write SetValue;
              end;
              
            implementation
            
            function TCalculatorImpl.Add(A, B: Integer): Integer;
            begin
              Result := A + B;
            end;
            
            function TCalculatorImpl.Subtract(A, B: Integer): Integer;
            begin
              Result := A - B;
            end;
            
            function TCalculatorImpl.GetValue: Integer;
            begin
              Result := FValue;
            end;
            
            procedure TCalculatorImpl.SetValue(const Value: Integer);
            begin
              FValue := Value;
            end;
            
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "Interfaces.pas")

        # Should find: unit, interface, class, multiple functions/procedures, properties
        assert len(chunks) >= 8

        # Check interface chunk
        interface_chunk = next(
            (c for c in chunks if c.semantic_type == "interface"), None
        )
        assert interface_chunk is not None
        assert interface_chunk.semantic_name == "ICalculator"
        assert interface_chunk.semantic_path == "Interfaces.ICalculator"

        # Check class implementation
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "TCalculatorImpl"
        assert "ICalculator" in str(class_chunk.semantic_context)

        # Check interface methods vs implementation methods
        interface_methods = [c for c in chunks if c.semantic_parent == "ICalculator"]
        impl_methods = [c for c in chunks if c.semantic_parent == "TCalculatorImpl"]

        assert len(interface_methods) >= 2  # Add, Subtract methods + property
        assert len(impl_methods) >= 4  # Add, Subtract, GetValue, SetValue

    def test_record_type_chunking(self, parser):
        """Test parsing record type declarations."""
        content = dedent(
            """
            unit Records;
            
            interface
            
            type
              TPoint = record
                X: Integer;
                Y: Integer;
                constructor Create(AX, AY: Integer);
                function Distance(const Other: TPoint): Double;
                class function Origin: TPoint; static;
              end;
              
              TRectangle = record
                TopLeft: TPoint;
                BottomRight: TPoint;
                function Width: Integer;
                function Height: Integer;
                function Area: Integer;
              end;
              
            implementation
            
            constructor TPoint.Create(AX, AY: Integer);
            begin
              X := AX;
              Y := AY;
            end;
            
            function TPoint.Distance(const Other: TPoint): Double;
            begin
              Result := Sqrt(Sqr(X - Other.X) + Sqr(Y - Other.Y));
            end;
            
            class function TPoint.Origin: TPoint;
            begin
              Result := TPoint.Create(0, 0);
            end;
            
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "Records.pas")

        # Should find: unit, records, constructor, functions
        assert len(chunks) >= 6

        # Check record chunks
        point_record = next((c for c in chunks if c.semantic_name == "TPoint"), None)
        assert point_record is not None
        assert point_record.semantic_type == "record"
        assert point_record.semantic_path == "Records.TPoint"

        rect_record = next((c for c in chunks if c.semantic_name == "TRectangle"), None)
        assert rect_record is not None
        assert rect_record.semantic_type == "record"

        # Check record methods
        distance_method = next(
            (c for c in chunks if c.semantic_name == "Distance"), None
        )
        assert distance_method is not None
        assert distance_method.semantic_parent == "TPoint"
        assert "Double" in distance_method.semantic_signature

        # Check static method
        origin_method = next((c for c in chunks if c.semantic_name == "Origin"), None)
        assert origin_method is not None
        assert "static" in str(origin_method.semantic_context).lower()

    def test_nested_procedures_and_functions(self, parser):
        """Test parsing nested procedures and functions."""
        content = dedent(
            """
            unit NestedFunctions;
            
            interface
            
            function ComplexCalculation(A, B: Integer): Integer;
            
            implementation
            
            function ComplexCalculation(A, B: Integer): Integer;
            
              function Helper1(X: Integer): Integer;
              begin
                Result := X * 2;
              end;
              
              procedure Helper2(var X: Integer);
              
                function DeepNested(Y: Integer): Integer;
                begin
                  Result := Y + 1;
                end;
                
              begin
                X := DeepNested(X) + 10;
              end;
              
            begin
              Result := Helper1(A) + Helper1(B);
              Helper2(Result);
            end;
            
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "NestedFunctions.pas")

        # Should find: unit, main function, nested functions/procedures
        assert len(chunks) >= 5

        # Check main function
        main_func = next(
            (c for c in chunks if c.semantic_name == "ComplexCalculation"), None
        )
        assert main_func is not None
        assert main_func.semantic_parent == "NestedFunctions"

        # Check nested functions have correct parent relationships
        helper1 = next((c for c in chunks if c.semantic_name == "Helper1"), None)
        assert helper1 is not None
        assert helper1.semantic_parent == "ComplexCalculation"

        helper2 = next((c for c in chunks if c.semantic_name == "Helper2"), None)
        assert helper2 is not None
        assert helper2.semantic_parent == "ComplexCalculation"

        deep_nested = next((c for c in chunks if c.semantic_name == "DeepNested"), None)
        assert deep_nested is not None
        assert deep_nested.semantic_parent == "Helper2"

    def test_property_declarations(self, parser):
        """Test parsing various property declaration styles."""
        content = dedent(
            """
            unit Properties;
            
            interface
            
            type
              TPropertyDemo = class
              private
                FReadOnly: Integer;
                FReadWrite: string;
                FWriteOnly: Boolean;
                function GetCalculated: Double;
                procedure SetWriteOnly(const Value: Boolean);
              public
                property ReadOnly: Integer read FReadOnly;
                property ReadWrite: string read FReadWrite write FReadWrite;
                property WriteOnly: Boolean write SetWriteOnly;
                property Calculated: Double read GetCalculated;
                property Indexed[Index: Integer]: string read GetIndexed write SetIndexed;
                property Default[Index: Integer]: Variant read GetDefault write SetDefault; default;
              end;
              
            implementation
            
            // Property getter/setter implementations would go here
            
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "Properties.pas")

        # Should find multiple property declarations
        property_chunks = [c for c in chunks if c.semantic_type == "property"]
        assert len(property_chunks) >= 6

        # Check different property types
        readonly_prop = next(
            (c for c in property_chunks if c.semantic_name == "ReadOnly"), None
        )
        assert readonly_prop is not None
        assert "read" in readonly_prop.semantic_signature
        assert "write" not in readonly_prop.semantic_signature

        readwrite_prop = next(
            (c for c in property_chunks if c.semantic_name == "ReadWrite"), None
        )
        assert readwrite_prop is not None
        assert "read" in readwrite_prop.semantic_signature
        assert "write" in readwrite_prop.semantic_signature

        indexed_prop = next(
            (c for c in property_chunks if c.semantic_name == "Indexed"), None
        )
        assert indexed_prop is not None
        assert "[Index: Integer]" in indexed_prop.semantic_signature

        default_prop = next(
            (c for c in property_chunks if c.semantic_name == "Default"), None
        )
        assert default_prop is not None
        assert "default" in str(default_prop.semantic_context).lower()

    def test_constants_and_variables(self, parser):
        """Test parsing constant and variable declarations."""
        content = dedent(
            """
            unit Constants;
            
            interface
            
            const
              PI = 3.14159;
              MAX_COUNT = 100;
              DEFAULT_NAME = 'Unknown';
              
            type
              TColor = (Red, Green, Blue);
              
            var
              GlobalCounter: Integer;
              ApplicationName: string;
              
            implementation
            
            const
              INTERNAL_BUFFER_SIZE = 1024;
              
            var
              InternalCache: array[0..99] of Integer;
              
            end.
        """
        ).strip()

        chunks = parser.chunk(content, "Constants.pas")

        # Should find constants, variables, and type declarations
        const_chunks = [c for c in chunks if c.semantic_type == "constant"]
        var_chunks = [c for c in chunks if c.semantic_type == "variable"]
        type_chunks = [c for c in chunks if c.semantic_type == "type"]

        assert (
            len(const_chunks) >= 4
        )  # PI, MAX_COUNT, DEFAULT_NAME, INTERNAL_BUFFER_SIZE
        assert len(var_chunks) >= 3  # GlobalCounter, ApplicationName, InternalCache
        assert len(type_chunks) >= 1  # TColor

        # Check specific constants
        pi_const = next((c for c in const_chunks if c.semantic_name == "PI"), None)
        assert pi_const is not None
        assert "3.14159" in pi_const.semantic_signature

        # Check enum type
        color_type = next((c for c in type_chunks if c.semantic_name == "TColor"), None)
        assert color_type is not None
        assert "Red, Green, Blue" in str(color_type.semantic_context)

    def test_malformed_pascal_code_handling(self, parser):
        """Test handling of malformed Pascal code."""
        malformed_content = """
            This is not valid Pascal code at all!
            It should not cause crashes.
            
            unit; // incomplete
            clas TTest // typo and missing 'end'
            procedure // incomplete
        """

        # Should not crash and should return empty or minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.pas")

        # Parser should handle gracefully - either empty chunks or safe fallback
        assert isinstance(chunks, list)

    def test_file_extension_detection(self, parser):
        """Test detection of different Pascal file extensions."""
        simple_content = """
            unit Test;
            interface
            implementation
            end.
        """

        # Test various Pascal file extensions
        extensions = [".pas", ".pp", ".dpr", ".dpk", ".inc"]

        for ext in extensions:
            chunks = parser.chunk(simple_content, f"test{ext}")
            assert len(chunks) >= 1
            assert chunks[0].file_extension == ext

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Pascal files."""
        content = dedent(
            """
            unit Integration;
            
            interface
            
            type
              TTest = class
                procedure DoSomething;
              end;
              
            implementation
            
            procedure TTest.DoSomething;
            begin
              // Implementation here
            end;
            
            end.
        """
        ).strip()

        chunks = chunker.chunk_content(content, "integration.pas")

        # Should get semantic chunks from Pascal parser
        assert len(chunks) >= 3  # unit, class, procedure

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

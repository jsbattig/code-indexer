// Intentionally broken Go file to test fallback chunking
package main

import (
    "fmt"
    // Missing import statement and quotes
    net/http
)

// Malformed struct definition
type BrokenStruct struct {
    Name string `json:"name"
    Age  int    `json:"age"`
    // Missing closing quote in struct tag
    Email string json:"email"
    // Missing backticks
}

// Invalid interface
type BrokenInterface interface {
    Method1() (string, error
    // Missing closing parenthesis
    Method2(param int) 
    // Missing return type
    Method3() (result, error)
    // Invalid parameter name in return
}

// Malformed function declaration
func BrokenFunction(param1 string, param2) (string, error) {
    // Missing type for param2
    
    if param1 == "" {
        return "", fmt.Errorf("param1 is empty"
        // Missing closing parenthesis
    }
    
    // Invalid variable declarations
    var result string =
    // Missing assignment value
    
    // Unclosed string literal
    message := "This string is never closed
    
    // Invalid array declaration
    arr := []int{1, 2, 3,
    // Missing closing brace
    
    // Malformed for loop
    for i := 0; i < len(arr) {
        // Missing increment statement and condition
        fmt.Println(arr[i])
    
    // Missing closing brace
    
    return result, nil
}

// Invalid method receiver
func (b *BrokenStruct Method() {
    // Missing closing parenthesis in receiver
    fmt.Println("This won't compile")
}

// Incomplete main function
func main() {
    s := BrokenStruct{
        Name: "Test",
        Age:  25,
        Email: 
        // Missing value
    }
    
    result, err := BrokenFunction(s.Name,)
    // Missing second parameter
    
    if err != nil {
        fmt.Printf("Error: %v\n", err)
    } else {
        fmt.Printf("Result: %s\n", result)
    }
// Missing closing brace for main
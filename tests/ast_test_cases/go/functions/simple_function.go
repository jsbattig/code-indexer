package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}

func add(a int, b int) int {
    return a + b
}

func divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("cannot divide by zero")
    }
    return a / b, nil
}
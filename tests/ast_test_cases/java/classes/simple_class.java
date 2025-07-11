public class Calculator {
    private int value;
    
    public Calculator(int initialValue) {
        this.value = initialValue;
    }
    
    public int add(int number) {
        return this.value + number;
    }
    
    public static int multiply(int a, int b) {
        return a * b;
    }
}
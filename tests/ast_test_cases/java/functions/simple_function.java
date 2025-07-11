public class MathUtils {
    public static int factorial(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }
    
    public static double calculateArea(double radius) {
        return Math.PI * radius * radius;
    }
}
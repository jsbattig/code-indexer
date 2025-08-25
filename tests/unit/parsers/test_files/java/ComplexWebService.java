package com.example.microservices.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.beans.factory.annotation.Autowired;
import javax.validation.Valid;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import javax.persistence.*;
import java.util.List;
import java.util.Optional;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * Complex Spring Boot microservice for order management
 * Demonstrates modern Java features and patterns
 */
@SpringBootApplication
@RestController
@RequestMapping("/api/v1/orders")
public class OrderMicroservice {

    @Autowired
    private OrderRepository orderRepository;
    
    @Autowired
    private PaymentService paymentService;

    public static void main(String[] args) {
        SpringApplication.run(OrderMicroservice.class, args);
    }

    @GetMapping
    public List<Order> getAllOrders() {
        return orderRepository.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable Long id) {
        Optional<Order> order = orderRepository.findById(id);
        return order.map(ResponseEntity::ok)
                   .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<Order> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        try {
            Order order = new Order(request.getCustomerId(), request.getItems());
            order.calculateTotal();
            
            // Process payment
            PaymentResult result = paymentService.processPayment(
                order.getTotalAmount(), 
                request.getPaymentMethod()
            );
            
            if (result.isSuccessful()) {
                order.setStatus(OrderStatus.CONFIRMED);
                Order savedOrder = orderRepository.save(order);
                return ResponseEntity.ok(savedOrder);
            } else {
                return ResponseEntity.badRequest().build();
            }
        } catch (Exception e) {
            return ResponseEntity.internalServerError().build();
        }
    }

    @PutMapping("/{id}/status")
    public ResponseEntity<Order> updateOrderStatus(
            @PathVariable Long id, 
            @RequestBody OrderStatusUpdate statusUpdate) {
        
        return orderRepository.findById(id)
                .map(order -> {
                    order.setStatus(statusUpdate.getStatus());
                    order.setUpdatedAt(LocalDateTime.now());
                    return ResponseEntity.ok(orderRepository.save(order));
                })
                .orElse(ResponseEntity.notFound().build());
    }
}

@Entity
@Table(name = "orders")
class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @OneToMany(cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private List<OrderItem> items;

    @Enumerated(EnumType.STRING)
    private OrderStatus status = OrderStatus.PENDING;

    @Column(name = "total_amount", precision = 10, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    protected Order() {} // JPA constructor

    public Order(Long customerId, List<OrderItem> items) {
        this.customerId = customerId;
        this.items = items;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    public void calculateTotal() {
        this.totalAmount = items.stream()
            .map(OrderItem::getSubtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    // Complex generic method with multiple type parameters
    public <T extends Comparable<T>, U> Optional<T> findMaxByProperty(
            List<U> items, 
            Function<U, T> propertyExtractor) {
        return items.stream()
                   .map(propertyExtractor)
                   .max(T::compareTo);
    }

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }

    public List<OrderItem> getItems() { return items; }
    public void setItems(List<OrderItem> items) { this.items = items; }

    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }

    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal totalAmount) { this.totalAmount = totalAmount; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}

@Entity
@Table(name = "order_items")
class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    @Column(name = "unit_price", precision = 8, scale = 2, nullable = false)
    private BigDecimal unitPrice;

    protected OrderItem() {} // JPA constructor

    public OrderItem(Long productId, Integer quantity, BigDecimal unitPrice) {
        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public BigDecimal getSubtotal() {
        return unitPrice.multiply(new BigDecimal(quantity));
    }

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getProductId() { return productId; }
    public void setProductId(Long productId) { this.productId = productId; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) { this.unitPrice = unitPrice; }
}

enum OrderStatus {
    PENDING("Pending"),
    CONFIRMED("Confirmed"),
    PROCESSING("Processing"),
    SHIPPED("Shipped"),
    DELIVERED("Delivered"),
    CANCELLED("Cancelled");

    private final String displayName;

    OrderStatus(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isActive() {
        return this != CANCELLED;
    }

    public static OrderStatus fromString(String status) {
        for (OrderStatus orderStatus : OrderStatus.values()) {
            if (orderStatus.name().equalsIgnoreCase(status)) {
                return orderStatus;
            }
        }
        throw new IllegalArgumentException("Unknown order status: " + status);
    }
}

interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByCustomerId(Long customerId);
    List<Order> findByStatus(OrderStatus status);
    List<Order> findByCreatedAtBetween(LocalDateTime start, LocalDateTime end);
    
    @Query("SELECT o FROM Order o WHERE o.totalAmount > :amount")
    List<Order> findExpensiveOrders(@Param("amount") BigDecimal amount);
}

@Service
class PaymentService {
    
    public PaymentResult processPayment(BigDecimal amount, PaymentMethod method) {
        // Complex payment processing logic
        switch (method) {
            case CREDIT_CARD:
                return processCreditCardPayment(amount);
            case PAYPAL:
                return processPayPalPayment(amount);
            case BANK_TRANSFER:
                return processBankTransferPayment(amount);
            default:
                throw new UnsupportedPaymentMethodException("Payment method not supported: " + method);
        }
    }

    private PaymentResult processCreditCardPayment(BigDecimal amount) {
        // Simulate credit card processing
        return new PaymentResult(true, "Transaction completed successfully");
    }

    private PaymentResult processPayPalPayment(BigDecimal amount) {
        // Simulate PayPal processing
        return new PaymentResult(true, "PayPal payment completed");
    }

    private PaymentResult processBankTransferPayment(BigDecimal amount) {
        // Simulate bank transfer processing
        return new PaymentResult(true, "Bank transfer initiated");
    }
}

// Nested classes and complex inheritance
abstract class BasePaymentProcessor {
    protected abstract boolean validatePayment(PaymentDetails details);
    
    public final PaymentResult process(PaymentDetails details) {
        if (validatePayment(details)) {
            return executePayment(details);
        }
        return new PaymentResult(false, "Payment validation failed");
    }
    
    protected abstract PaymentResult executePayment(PaymentDetails details);
    
    // Inner class for payment callbacks
    protected class PaymentCallback implements Callback<PaymentResult> {
        @Override
        public void onSuccess(PaymentResult result) {
            // Handle successful payment
        }
        
        @Override
        public void onError(Exception error) {
            // Handle payment error
        }
    }
}

// Record class (Java 14+)
record CreateOrderRequest(
    @NotNull Long customerId,
    @NotNull @Size(min = 1) List<OrderItemRequest> items,
    @NotNull PaymentMethod paymentMethod
) {
    // Compact constructor with validation
    public CreateOrderRequest {
        if (customerId <= 0) {
            throw new IllegalArgumentException("Customer ID must be positive");
        }
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("Order must contain at least one item");
        }
    }
    
    // Custom method in record
    public BigDecimal estimateTotal() {
        return items.stream()
                   .map(item -> item.unitPrice().multiply(new BigDecimal(item.quantity())))
                   .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
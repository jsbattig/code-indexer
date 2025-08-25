"""
Tests demonstrating improved search quality with cohesive chunking.
These tests validate that users get meaningful, complete chunks when searching
instead of fragmented assignment statements.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.ruby_parser import RubySemanticParser


class TestRubySearchQuality:
    """Test that search results provide meaningful, cohesive chunks."""

    @pytest.fixture
    def parser(self):
        """Create a Ruby parser directly."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RubySemanticParser(config)

    def test_search_for_initialize_returns_complete_method(self, parser):
        """
        When searching for 'initialize', users should get complete method
        implementation, not individual assignment fragments.
        """
        content = dedent(
            """
            class UserAccount
              def initialize(username, email, preferences = {})
                # Set basic user data
                @username = username
                @email = email
                @created_at = Time.current
                
                # Set preferences with defaults
                @notifications_enabled = preferences.fetch(:notifications, true)
                @theme = preferences.fetch(:theme, 'light')
                @language = preferences.fetch(:language, 'en')
                
                # Initialize collections
                @login_history = []
                @session_tokens = {}
                @preferences = preferences
                
                # Setup initial state
                @status = 'active'
                @last_login = nil
                @failed_attempts = 0
                
                # Validate the new account
                validate_email_format
                setup_default_permissions
                log_account_creation
              end
              
              def other_method
                @other_var = "something"
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "user_account.rb")

        # Find chunks that would be returned for "initialize" search
        initialize_chunks = [
            c
            for c in chunks
            if (
                "initialize" in c.semantic_name.lower()
                or "initialize" in c.text.lower()
            )
        ]

        # Should have exactly ONE meaningful chunk for initialize
        method_chunks = [c for c in initialize_chunks if c.semantic_type == "method"]
        assert (
            len(method_chunks) == 1
        ), f"Should find exactly 1 initialize method chunk, found {len(method_chunks)}"

        initialize_chunk = method_chunks[0]

        # Verify it's a complete, meaningful search result
        assert initialize_chunk.semantic_name == "initialize"
        assert (
            "def initialize(username, email, preferences = {})" in initialize_chunk.text
        )

        # Should contain ALL the method logic, not fragments
        complete_content = [
            "@username = username",
            "@email = email",
            "@created_at = Time.current",
            "@notifications_enabled = preferences.fetch(:notifications, true)",
            "@theme = preferences.fetch(:theme, 'light')",
            "@language = preferences.fetch(:language, 'en')",
            "@login_history = []",
            "@session_tokens = {}",
            "@preferences = preferences",
            "@status = 'active'",
            "@last_login = nil",
            "@failed_attempts = 0",
            "validate_email_format",
            "setup_default_permissions",
            "log_account_creation",
        ]

        for content_item in complete_content:
            assert (
                content_item in initialize_chunk.text
            ), f"Complete initialize method should contain '{content_item}'"

        # CRITICAL: Should NOT have meaningless assignment fragments as search results
        fragment_chunks = [
            c
            for c in initialize_chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name.startswith("@")
        ]

        assert len(fragment_chunks) == 0, (
            f"Search for 'initialize' should NOT return meaningless assignment fragments. "
            f"Found {len(fragment_chunks)} fragments: {[c.semantic_name for c in fragment_chunks]}"
        )

    def test_search_for_controller_action_returns_complete_logic(self, parser):
        """
        When searching for controller actions, users should get complete
        business logic, not individual instance variable assignments.
        """
        content = dedent(
            """
            class OrdersController < ApplicationController
              def create_order
                # Parse and validate input
                @order_params = order_params
                @user = current_user
                @billing_address = @order_params[:billing_address]
                @shipping_address = @order_params[:shipping_address] || @billing_address
                
                # Create the order
                @order = Order.new(user: @user)
                @order.billing_address = @billing_address
                @order.shipping_address = @shipping_address
                @order.status = 'pending'
                @order.order_number = generate_order_number
                
                # Process line items
                @line_items = build_line_items(@order_params[:items])
                @total_amount = calculate_total(@line_items)
                @tax_amount = calculate_tax(@total_amount, @billing_address)
                @final_amount = @total_amount + @tax_amount
                
                @order.line_items = @line_items
                @order.total_amount = @final_amount
                
                # Attempt to save and process payment
                if @order.save
                  @payment_result = process_payment(@order, @order_params[:payment])
                  
                  if @payment_result[:success]
                    @order.status = 'confirmed'
                    @order.save!
                    @success_message = "Order created successfully!"
                    @redirect_url = order_path(@order)
                    
                    # Send confirmations
                    OrderMailer.confirmation(@order).deliver_later
                    notify_inventory_system(@order)
                    
                    respond_with_success
                  else
                    @error_message = @payment_result[:error]
                    @order.destroy
                    respond_with_payment_error
                  end
                else
                  @validation_errors = @order.errors.full_messages
                  respond_with_validation_error
                end
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "orders_controller.rb")

        # Find chunks for "create_order" search
        create_order_chunks = [
            c
            for c in chunks
            if (
                "create_order" in c.semantic_name.lower()
                or "create_order" in c.text.lower()
            )
        ]

        # Should have exactly ONE meaningful chunk for create_order
        method_chunks = [c for c in create_order_chunks if c.semantic_type == "method"]
        assert (
            len(method_chunks) == 1
        ), f"Should find exactly 1 create_order method chunk, found {len(method_chunks)}"

        create_order_chunk = method_chunks[0]

        # Verify it contains complete business logic
        business_logic = [
            "@order_params = order_params",
            "@user = current_user",
            "@order = Order.new(user: @user)",
            "@line_items = build_line_items",
            "@total_amount = calculate_total",
            "@payment_result = process_payment",
            "OrderMailer.confirmation(@order).deliver_later",
            "notify_inventory_system(@order)",
            "respond_with_success",
            "respond_with_payment_error",
            "respond_with_validation_error",
        ]

        for logic_item in business_logic:
            assert (
                logic_item in create_order_chunk.text
            ), f"create_order should contain business logic: '{logic_item}'"

        # Should NOT return fragmented variable assignments
        order_variables = [
            "@order_params",
            "@user",
            "@billing_address",
            "@shipping_address",
            "@order",
            "@line_items",
            "@total_amount",
            "@tax_amount",
            "@payment_result",
            "@success_message",
            "@error_message",
        ]

        fragment_chunks = [
            c
            for c in create_order_chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in order_variables
        ]

        assert len(fragment_chunks) == 0, (
            f"Search for 'create_order' should NOT return variable fragments. "
            f"Found {len(fragment_chunks)} fragments: {[c.semantic_name for c in fragment_chunks]}"
        )

    def test_search_relevance_comparison_before_after_fix(self, parser):
        """
        Demonstrate the difference between fragmented vs cohesive results.
        This test shows what users would have gotten before vs after the fix.
        """
        content = dedent(
            """
            class PaymentProcessor
              def process_credit_card_payment(amount, card_details)
                # Validation phase
                @amount = amount
                @card_number = card_details[:number]
                @expiry_date = card_details[:expiry]
                @cvv = card_details[:cvv]
                @cardholder_name = card_details[:name]
                
                # Security checks
                @is_valid_card = validate_card_number(@card_number)
                @is_valid_expiry = validate_expiry(@expiry_date)
                @is_valid_cvv = validate_cvv(@cvv)
                @fraud_check_result = run_fraud_detection(@card_details)
                
                unless @is_valid_card && @is_valid_expiry && @is_valid_cvv
                  @error_message = "Invalid card details"
                  @error_code = "INVALID_CARD"
                  return build_error_response
                end
                
                if @fraud_check_result[:risk_level] == 'high'
                  @error_message = "Transaction blocked due to fraud risk"
                  @error_code = "FRAUD_DETECTED"
                  return build_error_response
                end
                
                # Process payment
                @transaction_id = generate_transaction_id
                @gateway_response = charge_card(@amount, @card_details, @transaction_id)
                
                if @gateway_response[:success]
                  @payment_status = 'completed'
                  @payment_reference = @gateway_response[:reference]
                  @confirmation_code = generate_confirmation_code
                  
                  # Log successful transaction
                  log_successful_payment(@transaction_id, @amount)
                  
                  return build_success_response
                else
                  @payment_status = 'failed'
                  @error_message = @gateway_response[:error_message]
                  @error_code = @gateway_response[:error_code]
                  
                  # Log failed transaction
                  log_failed_payment(@transaction_id, @error_code)
                  
                  return build_error_response
                end
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "payment_processor.rb")

        # AFTER THE FIX: Search for payment processing should return ONE meaningful chunk
        payment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "method"
            and "process_credit_card_payment" in c.semantic_name
        ]

        assert (
            len(payment_chunks) == 1
        ), "Should have exactly 1 cohesive payment processing chunk"

        payment_chunk = payment_chunks[0]

        # This chunk should contain ALL the payment logic - meaningful for developers
        payment_logic = [
            "# Validation phase",
            "# Security checks",
            "# Process payment",
            "@is_valid_card = validate_card_number",
            "@fraud_check_result = run_fraud_detection",
            "@gateway_response = charge_card",
            "log_successful_payment",
            "log_failed_payment",
            "return build_success_response",
            "return build_error_response",
        ]

        for logic in payment_logic:
            assert logic in payment_chunk.text, f"Payment chunk should contain: {logic}"

        # CRITICAL: Before the fix, users would get meaningless fragments like:
        # - "@amount = amount" (useless fragment)
        # - "@card_number = card_details[:number]" (useless fragment)
        # - "@cvv = card_details[:cvv]" (useless fragment)
        #
        # After the fix, they get the COMPLETE method with full context

        # Verify NO meaningless fragments exist
        payment_variables = [
            "@amount",
            "@card_number",
            "@expiry_date",
            "@cvv",
            "@cardholder_name",
            "@is_valid_card",
            "@is_valid_expiry",
            "@is_valid_cvv",
            "@fraud_check_result",
            "@error_message",
            "@error_code",
            "@transaction_id",
            "@gateway_response",
        ]

        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in payment_variables
        ]

        assert len(fragment_chunks) == 0, (
            f"After fix: Should have NO meaningless variable fragments. "
            f"Before fix: Would have had {len(payment_variables)} useless fragments. "
            f"Found: {[c.semantic_name for c in fragment_chunks]}"
        )

    def test_method_search_provides_actionable_context(self, parser):
        """
        Test that method searches provide actionable context for developers.
        This is what makes good search results vs bad search results.
        """
        content = dedent(
            """
            class EmailService
              def send_welcome_email(user, template_vars = {})
                # Prepare email data
                @user = user
                @user_email = @user.email
                @user_name = @user.full_name
                @template_vars = template_vars
                
                # Load template and merge variables
                @template = EmailTemplate.find_by(name: 'welcome')
                @template_content = @template.content
                @merged_content = merge_template_variables(@template_content, @template_vars)
                
                # Personalization
                @personalized_subject = personalize_subject(@template.subject, @user)
                @personalized_content = personalize_content(@merged_content, @user)
                
                # Tracking setup
                @tracking_id = generate_email_tracking_id(@user.id)
                @tracking_pixel = generate_tracking_pixel(@tracking_id)
                @personalized_content += @tracking_pixel
                
                # Email composition
                @email_data = {
                  to: @user_email,
                  subject: @personalized_subject,
                  html_content: @personalized_content,
                  tracking_id: @tracking_id,
                  user_id: @user.id
                }
                
                # Send via email service
                @send_result = EmailDeliveryService.send(@email_data)
                
                if @send_result[:success]
                  @delivery_status = 'sent'
                  @message_id = @send_result[:message_id]
                  @sent_at = Time.current
                  
                  # Log successful delivery
                  EmailLog.create!(
                    user_id: @user.id,
                    template_name: 'welcome',
                    status: @delivery_status,
                    message_id: @message_id,
                    tracking_id: @tracking_id,
                    sent_at: @sent_at
                  )
                  
                  return { success: true, message_id: @message_id, tracking_id: @tracking_id }
                else
                  @delivery_status = 'failed'
                  @error_message = @send_result[:error]
                  @error_code = @send_result[:error_code]
                  
                  # Log failed delivery
                  EmailLog.create!(
                    user_id: @user.id,
                    template_name: 'welcome',
                    status: @delivery_status,
                    error_message: @error_message,
                    error_code: @error_code,
                    tracking_id: @tracking_id
                  )
                  
                  return { success: false, error: @error_message, code: @error_code }
                end
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "email_service.rb")

        # Find the email method
        email_chunks = [
            c
            for c in chunks
            if c.semantic_type == "method" and "send_welcome_email" in c.semantic_name
        ]

        assert len(email_chunks) == 1, "Should find exactly 1 email method chunk"

        email_chunk = email_chunks[0]

        # GOOD SEARCH RESULT: Contains actionable context for developers
        # They can understand:
        # 1. How to call the method: send_welcome_email(user, template_vars = {})
        # 2. What it does: loads template, personalizes, sends email, logs result
        # 3. What it returns: success/failure hash with relevant data
        # 4. Error handling: logs failures, returns error details
        # 5. Side effects: creates EmailLog records

        actionable_context = [
            "def send_welcome_email(user, template_vars = {})",  # Method signature
            "# Prepare email data",  # Step 1: data prep
            "# Load template and merge variables",  # Step 2: templating
            "# Personalization",  # Step 3: personalization
            "# Tracking setup",  # Step 4: tracking
            "# Email composition",  # Step 5: composition
            "# Send via email service",  # Step 6: delivery
            "@send_result = EmailDeliveryService.send(@email_data)",  # Core action
            "if @send_result[:success]",  # Success path
            "EmailLog.create!",  # Side effects
            "return { success: true",  # Success return
            "return { success: false",  # Failure return
        ]

        for context in actionable_context:
            assert (
                context in email_chunk.text
            ), f"Email method should provide actionable context: '{context}'"

        # BAD SEARCH RESULT: Individual variable assignments would be useless
        # Examples of what users would get before the fix:
        # - "@user_email = @user.email" (tells them nothing useful)
        # - "@template_vars = template_vars" (just variable assignment)
        # - "@tracking_id = generate_email_tracking_id(@user.id)" (no context)

        email_variables = [
            "@user",
            "@user_email",
            "@user_name",
            "@template_vars",
            "@template",
            "@template_content",
            "@merged_content",
            "@personalized_subject",
            "@personalized_content",
            "@tracking_id",
            "@email_data",
            "@send_result",
        ]

        useless_fragments = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in email_variables
        ]

        assert len(useless_fragments) == 0, (
            f"Should have NO useless variable fragments. "
            f"Before fix would have had {len(email_variables)} useless results. "
            f"Now users get 1 meaningful, actionable method chunk instead."
        )

        # Verify the chunk is substantial and meaningful
        assert len(email_chunk.text) > 500, "Method chunk should be substantial"
        assert (
            email_chunk.text.count("\n") > 20
        ), "Method chunk should contain multiple lines of logic"
        assert (
            "def send_welcome_email" in email_chunk.text
        ), "Should contain method definition"
        assert "end" in email_chunk.text, "Should contain complete method body"

"""
Tests for Ruby parser with Rails-specific patterns.
Validates that the cohesive chunking works correctly with common Rails idioms.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.ruby_parser import RubySemanticParser


class TestRubyRailsPatterns:
    """Test Rails-specific patterns maintain proper chunking."""

    @pytest.fixture
    def parser(self):
        """Create a Ruby parser directly."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RubySemanticParser(config)

    def test_activerecord_model_cohesion(self, parser):
        """Test ActiveRecord model methods remain cohesive."""
        content = dedent(
            """
            class User < ApplicationRecord
              validates :email, presence: true, uniqueness: true
              has_many :posts, dependent: :destroy
              
              before_create :set_defaults
              after_save :send_notification
              
              def full_name
                @full_name = "#{first_name} #{last_name}"
                @full_name.strip
              end
              
              def update_profile(params)
                @name = params[:name]
                @email = params[:email]
                @bio = params[:bio]
                @updated_at = Time.current
                
                if save
                  @success = true
                  notify_profile_update
                else
                  @errors = errors.full_messages
                  @success = false
                end
                
                @success
              end
              
              private
              
              def set_defaults
                @created_at = Time.current
                @status = 'active'
                @role = 'user'
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "user.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Check update_profile method cohesion
        update_chunks = [
            c for c in method_chunks if c.semantic_name == "update_profile"
        ]
        assert len(update_chunks) == 1, "update_profile should be one cohesive chunk"

        update_chunk = update_chunks[0]
        update_text = update_chunk.text

        # Should contain all assignments and logic
        expected_elements = [
            "@name = params[:name]",
            "@email = params[:email]",
            "@bio = params[:bio]",
            "@updated_at = Time.current",
            "@success = true",
            "@errors = errors.full_messages",
            "@success = false",
            "notify_profile_update",
        ]

        for element in expected_elements:
            assert element in update_text, f"update_profile should contain '{element}'"

        # Should NOT have fragmented instance variable chunks
        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in ["@name", "@email", "@bio", "@success", "@errors"]
        ]
        assert len(fragment_chunks) == 0, "Rails methods should not be fragmented"

    def test_controller_action_cohesion(self, parser):
        """Test Rails controller actions maintain cohesion."""
        content = dedent(
            """
            class PostsController < ApplicationController
              before_action :authenticate_user!
              before_action :set_post, only: [:show, :edit, :update, :destroy]
              
              def create
                @post = Post.new(post_params)
                @post.user = current_user
                @post.published_at = Time.current
                
                if @post.save
                  @flash_message = 'Post created successfully'
                  @redirect_path = post_path(@post)
                  respond_to do |format|
                    format.html { redirect_to @redirect_path, notice: @flash_message }
                    format.json { render :show, status: :created, location: @post }
                  end
                else
                  @errors = @post.errors.full_messages
                  @error_count = @errors.length
                  respond_to do |format|
                    format.html { render :new }
                    format.json { render json: @errors, status: :unprocessable_entity }
                  end
                end
              end
              
              def update
                @previous_title = @post.title
                @post.updated_by = current_user.id
                
                if @post.update(post_params)
                  @changes = @post.previous_changes
                  @success = true
                  redirect_to @post, notice: 'Post was successfully updated.'
                else
                  @success = false
                  @validation_errors = @post.errors
                  render :edit
                end
              end
              
              private
              
              def set_post
                @post = Post.find(params[:id])
                @post_id = @post.id
                @post_title = @post.title
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "posts_controller.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Check create action cohesion
        create_chunks = [c for c in method_chunks if c.semantic_name == "create"]
        assert len(create_chunks) == 1, "create action should be one cohesive chunk"

        create_chunk = create_chunks[0]
        create_text = create_chunk.text

        # Should contain all controller logic
        controller_elements = [
            "@post = Post.new(post_params)",
            "@post.user = current_user",
            "@post.published_at = Time.current",
            "@flash_message = 'Post created successfully'",
            "@redirect_path = post_path(@post)",
            "@errors = @post.errors.full_messages",
            "@error_count = @errors.length",
            "respond_to do |format|",
        ]

        for element in controller_elements:
            assert element in create_text, f"create action should contain '{element}'"

        # Check update action cohesion
        update_chunks = [c for c in method_chunks if c.semantic_name == "update"]
        assert len(update_chunks) == 1, "update action should be one cohesive chunk"

        # Should NOT have controller instance variables as separate chunks
        controller_vars = [
            "@post",
            "@flash_message",
            "@redirect_path",
            "@errors",
            "@error_count",
            "@changes",
            "@success",
            "@validation_errors",
        ]

        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in controller_vars
        ]
        assert len(fragment_chunks) == 0, "Controller actions should not be fragmented"

    def test_rails_service_object_cohesion(self, parser):
        """Test Rails service objects maintain method cohesion."""
        content = dedent(
            """
            class UserRegistrationService
              def initialize(params)
                @params = params
                @user = nil
                @errors = []
              end
              
              def call
                @user = User.new(user_params)
                @user.status = 'pending'
                @user.confirmation_token = generate_token
                @user.confirmation_sent_at = Time.current
                
                if @user.save
                  @success = true
                  @confirmation_email = send_confirmation_email
                  @welcome_message = generate_welcome_message
                  log_successful_registration
                else
                  @success = false
                  @errors = @user.errors.full_messages
                  @error_summary = build_error_summary
                  log_failed_registration
                end
                
                build_result
              end
              
              private
              
              def build_result
                @result = {
                  success: @success,
                  user: @user,
                  errors: @errors,
                  message: @success ? @welcome_message : @error_summary
                }
                @result
              end
              
              def generate_token
                @token = SecureRandom.urlsafe_base64(32)
                @token_expiry = 24.hours.from_now
                @token
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "user_registration_service.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Check call method cohesion (main service method)
        call_chunks = [c for c in method_chunks if c.semantic_name == "call"]
        assert len(call_chunks) == 1, "Service call method should be one cohesive chunk"

        call_chunk = call_chunks[0]
        call_text = call_chunk.text

        # Should contain all service logic
        service_elements = [
            "@user = User.new(user_params)",
            "@user.status = 'pending'",
            "@user.confirmation_token = generate_token",
            "@success = true",
            "@confirmation_email = send_confirmation_email",
            "@welcome_message = generate_welcome_message",
            "@success = false",
            "@errors = @user.errors.full_messages",
            "@error_summary = build_error_summary",
            "build_result",
        ]

        for element in service_elements:
            assert (
                element in call_text
            ), f"Service call method should contain '{element}'"

        # Check other private methods maintain cohesion
        build_result_chunks = [
            c for c in method_chunks if c.semantic_name == "build_result"
        ]
        assert (
            len(build_result_chunks) == 1
        ), "build_result should be one cohesive chunk"

        generate_token_chunks = [
            c for c in method_chunks if c.semantic_name == "generate_token"
        ]
        assert (
            len(generate_token_chunks) == 1
        ), "generate_token should be one cohesive chunk"

        # Should NOT fragment service object instance variables
        service_vars = [
            "@user",
            "@success",
            "@errors",
            "@confirmation_email",
            "@welcome_message",
            "@error_summary",
            "@result",
            "@token",
        ]

        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in service_vars
        ]
        assert (
            len(fragment_chunks) == 0
        ), "Service object methods should not be fragmented"

    def test_rails_concern_module_cohesion(self, parser):
        """Test Rails concern modules maintain method cohesion."""
        content = dedent(
            """
            module Trackable
              extend ActiveSupport::Concern
              
              included do
                before_save :update_tracking_info
                validates :tracking_id, presence: true
              end
              
              def track_activity(action)
                @tracking_id = generate_tracking_id
                @activity_type = action
                @timestamp = Time.current
                @user_agent = request.user_agent if respond_to?(:request)
                @ip_address = request.remote_ip if respond_to?(:request)
                
                @activity_log = ActivityLog.create!(
                  trackable: self,
                  tracking_id: @tracking_id,
                  activity_type: @activity_type,
                  timestamp: @timestamp,
                  metadata: {
                    user_agent: @user_agent,
                    ip_address: @ip_address
                  }
                )
                
                @tracking_successful = @activity_log.persisted?
                notify_tracking_complete if @tracking_successful
                @tracking_successful
              end
              
              def update_tracking_status(status)
                @old_status = self.tracking_status
                @new_status = status
                @status_changed = @old_status != @new_status
                
                if @status_changed
                  @update_time = Time.current
                  self.tracking_status = @new_status
                  self.status_updated_at = @update_time
                  @tracking_history = build_status_history
                  save_tracking_history
                end
                
                @status_changed
              end
              
              private
              
              def generate_tracking_id
                @prefix = self.class.name.downcase
                @timestamp_part = Time.current.to_i
                @random_part = SecureRandom.hex(8)
                @tracking_id = "#{@prefix}_#{@timestamp_part}_#{@random_part}"
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "trackable.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Check track_activity method cohesion
        track_chunks = [c for c in method_chunks if c.semantic_name == "track_activity"]
        assert len(track_chunks) == 1, "track_activity should be one cohesive chunk"

        track_chunk = track_chunks[0]
        track_text = track_chunk.text

        # Should contain all tracking logic
        tracking_elements = [
            "@tracking_id = generate_tracking_id",
            "@activity_type = action",
            "@timestamp = Time.current",
            "@user_agent = request.user_agent",
            "@ip_address = request.remote_ip",
            "@activity_log = ActivityLog.create!",
            "@tracking_successful = @activity_log.persisted?",
            "notify_tracking_complete if @tracking_successful",
        ]

        for element in tracking_elements:
            assert element in track_text, f"track_activity should contain '{element}'"

        # Check update_tracking_status method cohesion
        update_status_chunks = [
            c for c in method_chunks if c.semantic_name == "update_tracking_status"
        ]
        assert (
            len(update_status_chunks) == 1
        ), "update_tracking_status should be one cohesive chunk"

        # Should NOT fragment concern method variables
        concern_vars = [
            "@tracking_id",
            "@activity_type",
            "@timestamp",
            "@user_agent",
            "@ip_address",
            "@activity_log",
            "@tracking_successful",
            "@old_status",
            "@new_status",
            "@status_changed",
        ]

        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in concern_vars
        ]
        assert (
            len(fragment_chunks) == 0
        ), "Rails concern methods should not be fragmented"

    def test_rails_migration_cohesion(self, parser):
        """Test Rails migration methods maintain cohesion."""
        content = dedent(
            """
            class CreateUsersTable < ActiveRecord::Migration[7.0]
              def up
                @table_name = :users
                @primary_key = :id
                @created_at_column = :created_at
                @updated_at_column = :updated_at
                
                create_table @table_name, id: @primary_key do |t|
                  t.string :first_name, null: false
                  t.string :last_name, null: false
                  t.string :email, null: false
                  t.integer :age
                  t.boolean :active, default: true
                  
                  t.timestamps
                end
                
                @index_name = "index_users_on_email"
                @unique_index = true
                add_index @table_name, :email, name: @index_name, unique: @unique_index
                
                @constraint_added = true
                execute "ALTER TABLE users ADD CONSTRAINT check_age CHECK (age >= 0)"
              end
              
              def down
                @table_name = :users
                @index_name = "index_users_on_email"
                
                remove_index @table_name, name: @index_name if index_exists?(@table_name, :email)
                drop_table @table_name
                
                @migration_reversed = true
              end
              
              def change
                @reversible_operation = true
                @table_options = { id: :bigint }
                
                create_table :users, **@table_options do |t|
                  t.string :name, null: false
                  t.string :email, null: false, index: { unique: true }
                  
                  t.timestamps
                end
                
                @table_created = true
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "create_users_table.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Check up method cohesion
        up_chunks = [c for c in method_chunks if c.semantic_name == "up"]
        assert len(up_chunks) == 1, "Migration up method should be one cohesive chunk"

        up_chunk = up_chunks[0]
        up_text = up_chunk.text

        # Should contain all migration logic
        migration_elements = [
            "@table_name = :users",
            "@primary_key = :id",
            "@created_at_column = :created_at",
            "create_table @table_name",
            '@index_name = "index_users_on_email"',
            "@unique_index = true",
            "add_index @table_name, :email",
            "@constraint_added = true",
        ]

        for element in migration_elements:
            assert element in up_text, f"Migration up method should contain '{element}'"

        # Check down method cohesion
        down_chunks = [c for c in method_chunks if c.semantic_name == "down"]
        assert (
            len(down_chunks) == 1
        ), "Migration down method should be one cohesive chunk"

        # Should NOT fragment migration variables
        migration_vars = [
            "@table_name",
            "@primary_key",
            "@index_name",
            "@unique_index",
            "@constraint_added",
            "@migration_reversed",
            "@reversible_operation",
        ]

        fragment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in migration_vars
        ]
        assert (
            len(fragment_chunks) == 0
        ), "Rails migration methods should not be fragmented"

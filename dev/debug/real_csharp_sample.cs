using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace UserService.Controllers
{
    /// <summary>
    /// API controller for managing users
    /// </summary>
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        private readonly IUserRepository _userRepository;
        private readonly ILogger<UsersController> _logger;

        public UsersController(
            IUserRepository userRepository,
            ILogger<UsersController> logger)
        {
            _userRepository = userRepository ?? throw new ArgumentNullException(nameof(userRepository));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        /// <summary>
        /// Get all users with pagination
        /// </summary>
        [HttpGet]
        public async Task<ActionResult<PagedResult<UserDto>>> GetUsersAsync(
            [FromQuery] int page = 1,
            [FromQuery] int pageSize = 10,
            CancellationToken cancellationToken = default)
        {
            try
            {
                var users = await _userRepository.GetPagedAsync(page, pageSize, cancellationToken);
                return Ok(users);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error retrieving users");
                return StatusCode(500, "Internal server error");
            }
        }

        /// <summary>
        /// Get user by ID
        /// </summary>
        [HttpGet("{id:int}")]
        public async Task<ActionResult<UserDto>> GetUserByIdAsync(
            int id,
            CancellationToken cancellationToken = default)
        {
            if (id <= 0)
                return BadRequest("Invalid user ID");

            var user = await _userRepository.GetByIdAsync(id, cancellationToken);
            if (user == null)
                return NotFound();

            return Ok(user);
        }

        /// <summary>
        /// Create a new user
        /// </summary>
        [HttpPost]
        public async Task<ActionResult<UserDto>> CreateUserAsync(
            [FromBody] CreateUserRequest request,
            CancellationToken cancellationToken = default)
        {
            if (!ModelState.IsValid)
                return BadRequest(ModelState);

            var user = await _userRepository.CreateAsync(request, cancellationToken);
            return CreatedAtAction(nameof(GetUserByIdAsync), new { id = user.Id }, user);
        }

        /// <summary>
        /// Update an existing user
        /// </summary>
        [HttpPut("{id:int}")]
        public async Task<ActionResult<UserDto>> UpdateUserAsync(
            int id,
            [FromBody] UpdateUserRequest request,
            CancellationToken cancellationToken = default)
        {
            if (id <= 0)
                return BadRequest("Invalid user ID");

            if (!ModelState.IsValid)
                return BadRequest(ModelState);

            var user = await _userRepository.UpdateAsync(id, request, cancellationToken);
            if (user == null)
                return NotFound();

            return Ok(user);
        }

        /// <summary>
        /// Delete a user
        /// </summary>
        [HttpDelete("{id:int}")]
        public async Task<ActionResult> DeleteUserAsync(
            int id,
            CancellationToken cancellationToken = default)
        {
            if (id <= 0)
                return BadRequest("Invalid user ID");

            var deleted = await _userRepository.DeleteAsync(id, cancellationToken);
            if (!deleted)
                return NotFound();

            return NoContent();
        }

        /// <summary>
        /// Search users by criteria
        /// </summary>
        [HttpPost("search")]
        public async Task<ActionResult<PagedResult<UserDto>>> SearchUsersAsync(
            [FromBody] UserSearchCriteria criteria,
            CancellationToken cancellationToken = default)
        {
            var results = await _userRepository.SearchAsync(criteria, cancellationToken);
            return Ok(results);
        }
    }

    public class UserDto
    {
        public int Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Email { get; set; } = string.Empty;
        public DateTime CreatedAt { get; set; }
        public DateTime? UpdatedAt { get; set; }
        public bool IsActive { get; set; } = true;
        
        public string DisplayName => $"{Name} <{Email}>";
        public bool IsRecentlyUpdated => UpdatedAt?.AddDays(7) > DateTime.UtcNow;
    }

    public record CreateUserRequest(
        string Name,
        string Email,
        bool IsActive = true);

    public record UpdateUserRequest(
        string? Name = null,
        string? Email = null,
        bool? IsActive = null);

    public class UserSearchCriteria
    {
        public string? NameFilter { get; set; }
        public string? EmailFilter { get; set; }
        public bool? IsActive { get; set; }
        public DateTime? CreatedAfter { get; set; }
        public int Page { get; set; } = 1;
        public int PageSize { get; set; } = 10;
    }

    public class PagedResult<T>
    {
        public IEnumerable<T> Items { get; set; } = Enumerable.Empty<T>();
        public int TotalCount { get; set; }
        public int Page { get; set; }
        public int PageSize { get; set; }
        public int TotalPages => (int)Math.Ceiling((double)TotalCount / PageSize);
        public bool HasNextPage => Page < TotalPages;
        public bool HasPreviousPage => Page > 1;
    }

    public interface IUserRepository
    {
        Task<PagedResult<UserDto>> GetPagedAsync(int page, int pageSize, CancellationToken cancellationToken = default);
        Task<UserDto?> GetByIdAsync(int id, CancellationToken cancellationToken = default);
        Task<UserDto> CreateAsync(CreateUserRequest request, CancellationToken cancellationToken = default);
        Task<UserDto?> UpdateAsync(int id, UpdateUserRequest request, CancellationToken cancellationToken = default);
        Task<bool> DeleteAsync(int id, CancellationToken cancellationToken = default);
        Task<PagedResult<UserDto>> SearchAsync(UserSearchCriteria criteria, CancellationToken cancellationToken = default);
    }
}
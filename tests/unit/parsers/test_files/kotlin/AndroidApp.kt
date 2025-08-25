package com.example.androidapp

import android.app.Application
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path
import javax.inject.Inject
import javax.inject.Singleton

// Application class
@AndroidEntryPoint
class MyApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        initializeLogging()
    }

    private fun initializeLogging() {
        // Initialize logging framework
    }
}

// Data classes with modern Kotlin features
@Stable
data class User(
    val id: Long,
    val name: String,
    val email: String,
    val profilePicture: String? = null,
    val isVerified: Boolean = false,
    val preferences: UserPreferences = UserPreferences()
) {
    fun getDisplayName(): String = name.takeIf { it.isNotBlank() } ?: "Unknown User"
    
    companion object {
        fun createGuest(): User = User(
            id = 0L,
            name = "Guest",
            email = "guest@example.com"
        )
    }
}

data class UserPreferences(
    val theme: Theme = Theme.SYSTEM,
    val notifications: Boolean = true,
    val language: String = "en"
)

enum class Theme(val displayName: String) {
    LIGHT("Light"),
    DARK("Dark"),
    SYSTEM("System Default");
    
    fun isDarkMode(isSystemDark: Boolean): Boolean = when (this) {
        LIGHT -> false
        DARK -> true
        SYSTEM -> isSystemDark
    }
}

// Sealed class for UI state
sealed class UiState<out T> {
    object Loading : UiState<Nothing>()
    data class Success<T>(val data: T) : UiState<T>()
    data class Error(val exception: Throwable, val message: String = exception.message ?: "Unknown error") : UiState<Nothing>()
    
    inline fun <R> fold(
        onLoading: () -> R,
        onSuccess: (T) -> R,
        onError: (Throwable, String) -> R
    ): R = when (this) {
        is Loading -> onLoading()
        is Success -> onSuccess(data)
        is Error -> onError(exception, message)
    }
}

// Repository interface and implementation
interface UserRepository {
    suspend fun getUser(id: Long): Result<User>
    suspend fun updateUser(user: User): Result<User>
    fun observeUser(id: Long): Flow<User?>
}

@Singleton
class UserRepositoryImpl @Inject constructor(
    private val api: UserApiService,
    private val localDataSource: UserLocalDataSource
) : UserRepository {
    
    override suspend fun getUser(id: Long): Result<User> = try {
        val response = api.getUser(id)
        if (response.isSuccessful) {
            response.body()?.let { user ->
                localDataSource.cacheUser(user)
                Result.success(user)
            } ?: Result.failure(Exception("Empty response body"))
        } else {
            Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
        }
    } catch (e: Exception) {
        // Try local data as fallback
        localDataSource.getUser(id)?.let { 
            Result.success(it) 
        } ?: Result.failure(e)
    }
    
    override suspend fun updateUser(user: User): Result<User> = try {
        val response = api.updateUser(user.id, user)
        if (response.isSuccessful) {
            response.body()?.let { updatedUser ->
                localDataSource.cacheUser(updatedUser)
                Result.success(updatedUser)
            } ?: Result.failure(Exception("Empty response body"))
        } else {
            Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
    
    override fun observeUser(id: Long): Flow<User?> = 
        localDataSource.observeUser(id)
            .combine(flowOf(Unit).flatMapLatest { 
                flow { 
                    emit(getUser(id).getOrNull()) 
                }
            }) { cached, remote ->
                remote ?: cached
            }
}

// Network interface
interface UserApiService {
    @GET("users/{id}")
    suspend fun getUser(@Path("id") id: Long): Response<User>
    
    @GET("users/{id}")
    suspend fun updateUser(@Path("id") id: Long, user: User): Response<User>
}

// Local data source
@Singleton  
class UserLocalDataSource @Inject constructor() {
    private val _users = MutableStateFlow<Map<Long, User>>(emptyMap())
    
    suspend fun cacheUser(user: User) {
        _users.update { users -> 
            users + (user.id to user) 
        }
    }
    
    suspend fun getUser(id: Long): User? = _users.value[id]
    
    fun observeUser(id: Long): Flow<User?> = _users.map { users -> 
        users[id] 
    }
}

// ViewModel with coroutines
class UserViewModel @Inject constructor(
    private val repository: UserRepository
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<UiState<User>>(UiState.Loading)
    val uiState: StateFlow<UiState<User>> = _uiState.asStateFlow()
    
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()
    
    fun loadUser(userId: Long) {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            
            try {
                repository.getUser(userId)
                    .onSuccess { user ->
                        _uiState.value = UiState.Success(user)
                    }
                    .onFailure { exception ->
                        _uiState.value = UiState.Error(exception)
                    }
            } catch (e: Exception) {
                _uiState.value = UiState.Error(e)
            }
        }
    }
    
    fun refreshUser(userId: Long) {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                repository.getUser(userId)
                    .onSuccess { user ->
                        _uiState.value = UiState.Success(user)
                    }
                    .onFailure { exception ->
                        // Keep current state but show error
                        _uiState.value = UiState.Error(exception)
                    }
            } finally {
                _isRefreshing.value = false
            }
        }
    }
    
    fun updateUser(user: User) {
        viewModelScope.launch {
            repository.updateUser(user)
                .onSuccess { updatedUser ->
                    _uiState.value = UiState.Success(updatedUser)
                }
                .onFailure { exception ->
                    _uiState.value = UiState.Error(exception)
                }
        }
    }
}

// Activity with Compose
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MyAppTheme {
                AppNavigation()
            }
        }
    }
}

// Composable functions
@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    
    NavHost(
        navController = navController,
        startDestination = "user_profile"
    ) {
        composable("user_profile") {
            UserProfileScreen(
                onNavigateToSettings = { 
                    navController.navigate("settings") 
                }
            )
        }
        
        composable("settings") {
            SettingsScreen(
                onNavigateBack = { 
                    navController.popBackStack() 
                }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UserProfileScreen(
    onNavigateToSettings: () -> Unit,
    viewModel: UserViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()
    
    LaunchedEffect(Unit) {
        viewModel.loadUser(1L)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("User Profile") },
                actions = {
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Settings"
                        )
                    }
                }
            )
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentAlignment = Alignment.Center
        ) {
            when (uiState) {
                is UiState.Loading -> {
                    CircularProgressIndicator()
                }
                
                is UiState.Success -> {
                    UserContent(
                        user = uiState.data,
                        isRefreshing = isRefreshing,
                        onRefresh = { viewModel.refreshUser(uiState.data.id) },
                        onUpdateUser = viewModel::updateUser
                    )
                }
                
                is UiState.Error -> {
                    ErrorContent(
                        message = uiState.message,
                        onRetry = { viewModel.loadUser(1L) }
                    )
                }
            }
        }
    }
}

@Composable
fun UserContent(
    user: User,
    isRefreshing: Boolean,
    onRefresh: () -> Unit,
    onUpdateUser: (User) -> Unit
) {
    var showEditDialog by remember { mutableStateOf(false) }
    
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // User Avatar
        AsyncImage(
            model = user.profilePicture ?: "https://via.placeholder.com/100",
            contentDescription = "Profile Picture",
            modifier = Modifier
                .size(100.dp)
                .clip(CircleShape)
        )
        
        // User Info
        Text(
            text = user.getDisplayName(),
            style = MaterialTheme.typography.headlineMedium
        )
        
        Text(
            text = user.email,
            style = MaterialTheme.typography.bodyLarge
        )
        
        if (user.isVerified) {
            Row(
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Verified,
                    contentDescription = "Verified",
                    tint = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "Verified",
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
        
        // Action Buttons
        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Button(
                onClick = onRefresh,
                enabled = !isRefreshing
            ) {
                if (isRefreshing) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Refresh")
                }
            }
            
            OutlinedButton(
                onClick = { showEditDialog = true }
            ) {
                Text("Edit")
            }
        }
    }
    
    // Edit Dialog
    if (showEditDialog) {
        EditUserDialog(
            user = user,
            onDismiss = { showEditDialog = false },
            onConfirm = { updatedUser ->
                onUpdateUser(updatedUser)
                showEditDialog = false
            }
        )
    }
}

@Composable
fun ErrorContent(
    message: String,
    onRetry: () -> Unit
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Icon(
            imageVector = Icons.Default.Error,
            contentDescription = "Error",
            tint = MaterialTheme.colorScheme.error,
            modifier = Modifier.size(48.dp)
        )
        
        Text(
            text = "Something went wrong",
            style = MaterialTheme.typography.headlineSmall
        )
        
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        
        Button(onClick = onRetry) {
            Text("Retry")
        }
    }
}

@Composable
fun EditUserDialog(
    user: User,
    onDismiss: () -> Unit,
    onConfirm: (User) -> Unit
) {
    var name by remember { mutableStateOf(user.name) }
    var email by remember { mutableStateOf(user.email) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit User") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") }
                )
                
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") }
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { 
                    onConfirm(user.copy(name = name, email = email))
                }
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

@Composable
fun SettingsScreen(onNavigateBack: () -> Unit) {
    // Settings implementation
}

@Composable
fun MyAppTheme(content: @Composable () -> Unit) {
    MaterialTheme(content = content)
}

// Extension functions
fun String.isValidEmail(): Boolean = 
    isNotBlank() && contains("@") && contains(".")

fun User.toDisplayString(): String = "$name <$email>"

// Helper objects and utilities
object UserDefaults {
    const val GUEST_USER_ID = 0L
    const val DEFAULT_PROFILE_PICTURE = "https://via.placeholder.com/100"
    
    fun createDefaultPreferences(): UserPreferences = UserPreferences()
}

// Custom operators
infix fun String.hasPrefix(prefix: String): Boolean = startsWith(prefix)
infix fun String.hasSuffix(suffix: String): Boolean = endsWith(suffix)
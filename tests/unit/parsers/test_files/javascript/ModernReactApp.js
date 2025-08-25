// Modern React application with hooks, context, and advanced patterns
import React, { 
    useState, 
    useEffect, 
    useContext, 
    useReducer, 
    useCallback, 
    useMemo,
    useRef,
    forwardRef,
    memo
} from 'react';
import PropTypes from 'prop-types';
import { createContext } from 'react';

// Modern ES6+ imports and exports
export { default as UserProfile } from './UserProfile';
export { UserContext, useUser } from './hooks/useUser';
import * as userUtils from './utils/userUtils';
import { debounce, throttle } from 'lodash-es';

/**
 * Application Context for global state management
 * Uses modern Context API patterns
 */
const AppContext = createContext({
    user: null,
    theme: 'light',
    preferences: {},
    actions: {}
});

/**
 * Complex reducer for application state management
 * Demonstrates modern Redux-like patterns without Redux
 */
function appReducer(state, action) {
    switch (action.type) {
        case 'SET_USER':
            return {
                ...state,
                user: action.payload,
                isAuthenticated: !!action.payload
            };
        
        case 'UPDATE_PREFERENCES':
            return {
                ...state,
                preferences: {
                    ...state.preferences,
                    ...action.payload
                }
            };
        
        case 'TOGGLE_THEME':
            return {
                ...state,
                theme: state.theme === 'light' ? 'dark' : 'light'
            };
        
        case 'SET_LOADING':
            return {
                ...state,
                loading: {
                    ...state.loading,
                    [action.key]: action.value
                }
            };
        
        default:
            throw new Error(`Unknown action type: ${action.type}`);
    }
}

/**
 * Custom hook for managing complex async operations
 * Demonstrates advanced hook patterns and cleanup
 */
const useAsyncOperation = (asyncFunction, dependencies = []) => {
    const [state, setState] = useState({
        data: null,
        loading: false,
        error: null
    });
    
    const mountedRef = useRef(true);

    useEffect(() => {
        return () => { mountedRef.current = false; };
    }, []);

    const execute = useCallback(async (...args) => {
        setState(prevState => ({ ...prevState, loading: true, error: null }));
        
        try {
            const result = await asyncFunction(...args);
            
            if (mountedRef.current) {
                setState({
                    data: result,
                    loading: false,
                    error: null
                });
            }
            
            return result;
        } catch (error) {
            if (mountedRef.current) {
                setState({
                    data: null,
                    loading: false,
                    error
                });
            }
            throw error;
        }
    }, dependencies);

    return { ...state, execute };
};

/**
 * Complex functional component with multiple hooks and patterns
 * Demonstrates modern React component patterns
 */
const UserDashboard = memo(({ userId, onUserUpdate, className = '' }) => {
    // Multiple state hooks
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedTab, setSelectedTab] = useState('profile');
    const [notifications, setNotifications] = useState([]);
    
    // Reducer hook for complex state
    const [appState, dispatch] = useReducer(appReducer, {
        user: null,
        theme: 'light',
        preferences: {},
        loading: {},
        isAuthenticated: false
    });

    // Ref hooks
    const searchInputRef = useRef(null);
    const previousUserIdRef = useRef();

    // Context hook
    const { user, preferences, updateUser } = useContext(AppContext);

    // Custom hook usage
    const {
        data: userData,
        loading: userLoading,
        error: userError,
        execute: fetchUser
    } = useAsyncOperation(async (id) => {
        const response = await fetch(`/api/users/${id}`);
        if (!response.ok) throw new Error('Failed to fetch user');
        return response.json();
    }, []);

    // Complex effect with cleanup and dependencies
    useEffect(() => {
        if (userId !== previousUserIdRef.current) {
            fetchUser(userId);
            previousUserIdRef.current = userId;
        }
    }, [userId, fetchUser]);

    // Effect for WebSocket connection with cleanup
    useEffect(() => {
        const ws = new WebSocket(`ws://localhost:8080/users/${userId}`);
        
        ws.onmessage = (event) => {
            const notification = JSON.parse(event.data);
            setNotifications(prev => [...prev, notification]);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        return () => {
            ws.close();
        };
    }, [userId]);

    // Memoized values to prevent unnecessary recalculations
    const filteredNotifications = useMemo(() => {
        return notifications.filter(notification => 
            notification.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
            notification.message.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [notifications, searchTerm]);

    // Memoized callback with debouncing
    const debouncedSearch = useMemo(
        () => debounce((term) => {
            // Perform search API call
            console.log('Searching for:', term);
        }, 300),
        []
    );

    // Callback hooks to prevent unnecessary re-renders
    const handleSearchChange = useCallback((event) => {
        const value = event.target.value;
        setSearchTerm(value);
        debouncedSearch(value);
    }, [debouncedSearch]);

    const handleTabChange = useCallback((tab) => {
        setSelectedTab(tab);
        // Track tab change analytics
        window.gtag?.('event', 'tab_change', {
            event_category: 'user_dashboard',
            event_label: tab
        });
    }, []);

    const handleNotificationDismiss = useCallback((notificationId) => {
        setNotifications(prev => 
            prev.filter(notification => notification.id !== notificationId)
        );
    }, []);

    // Complex async function with error handling
    const handleUserUpdate = useCallback(async (updates) => {
        try {
            dispatch({ type: 'SET_LOADING', key: 'userUpdate', value: true });
            
            const response = await fetch(`/api/users/${userId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify(updates)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const updatedUser = await response.json();
            
            dispatch({ type: 'SET_USER', payload: updatedUser });
            onUserUpdate?.(updatedUser);
            
            // Show success notification
            setNotifications(prev => [...prev, {
                id: Date.now(),
                type: 'success',
                title: 'Profile Updated',
                message: 'Your profile has been successfully updated.'
            }]);

        } catch (error) {
            console.error('Error updating user:', error);
            
            setNotifications(prev => [...prev, {
                id: Date.now(),
                type: 'error',
                title: 'Update Failed',
                message: error.message || 'Failed to update profile.'
            }]);
        } finally {
            dispatch({ type: 'SET_LOADING', key: 'userUpdate', value: false });
        }
    }, [userId, onUserUpdate, dispatch]);

    // Cleanup effect
    useEffect(() => {
        return () => {
            debouncedSearch.cancel();
        };
    }, [debouncedSearch]);

    // Early return for loading state
    if (userLoading && !userData) {
        return (
            <div className={`dashboard-loading ${className}`}>
                <Spinner size="large" />
                <p>Loading user dashboard...</p>
            </div>
        );
    }

    // Early return for error state
    if (userError) {
        return (
            <ErrorBoundary
                error={userError}
                onRetry={() => fetchUser(userId)}
                className={className}
            />
        );
    }

    return (
        <div className={`user-dashboard ${appState.theme}-theme ${className}`}>
            <header className="dashboard-header">
                <SearchInput
                    ref={searchInputRef}
                    value={searchTerm}
                    onChange={handleSearchChange}
                    placeholder="Search notifications..."
                />
                
                <ThemeToggle
                    theme={appState.theme}
                    onToggle={() => dispatch({ type: 'TOGGLE_THEME' })}
                />
            </header>

            <nav className="dashboard-nav">
                <TabButton
                    active={selectedTab === 'profile'}
                    onClick={() => handleTabChange('profile')}
                >
                    Profile
                </TabButton>
                <TabButton
                    active={selectedTab === 'settings'}
                    onClick={() => handleTabChange('settings')}
                >
                    Settings
                </TabButton>
                <TabButton
                    active={selectedTab === 'notifications'}
                    onClick={() => handleTabChange('notifications')}
                >
                    Notifications ({filteredNotifications.length})
                </TabButton>
            </nav>

            <main className="dashboard-content">
                {selectedTab === 'profile' && (
                    <ProfilePanel
                        user={userData}
                        onUpdate={handleUserUpdate}
                        loading={appState.loading.userUpdate}
                    />
                )}
                
                {selectedTab === 'settings' && (
                    <SettingsPanel
                        preferences={appState.preferences}
                        onUpdate={(prefs) => 
                            dispatch({ type: 'UPDATE_PREFERENCES', payload: prefs })
                        }
                    />
                )}
                
                {selectedTab === 'notifications' && (
                    <NotificationList
                        notifications={filteredNotifications}
                        onDismiss={handleNotificationDismiss}
                    />
                )}
            </main>
        </div>
    );
});

UserDashboard.propTypes = {
    userId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    onUserUpdate: PropTypes.func,
    className: PropTypes.string
};

UserDashboard.displayName = 'UserDashboard';

// Forward ref component
const SearchInput = forwardRef(({ value, onChange, placeholder, ...props }, ref) => {
    return (
        <div className="search-input-container">
            <input
                ref={ref}
                type="text"
                value={value}
                onChange={onChange}
                placeholder={placeholder}
                className="search-input"
                {...props}
            />
            <SearchIcon className="search-icon" />
        </div>
    );
});

SearchInput.displayName = 'SearchInput';

// Higher-order component pattern
const withErrorBoundary = (WrappedComponent) => {
    return class extends React.Component {
        constructor(props) {
            super(props);
            this.state = { hasError: false, error: null };
        }

        static getDerivedStateFromError(error) {
            return { hasError: true, error };
        }

        componentDidCatch(error, errorInfo) {
            console.error('Error caught by boundary:', error, errorInfo);
            
            // Send error to monitoring service
            window.Sentry?.captureException(error, {
                contexts: { errorInfo }
            });
        }

        render() {
            if (this.state.hasError) {
                return (
                    <div className="error-boundary">
                        <h2>Something went wrong</h2>
                        <details>
                            <summary>Error details</summary>
                            <pre>{this.state.error?.stack}</pre>
                        </details>
                        <button onClick={() => this.setState({ hasError: false, error: null })}>
                            Try again
                        </button>
                    </div>
                );
            }

            return <WrappedComponent {...this.props} />;
        }
    };
};

// Complex async component with dynamic imports
const LazyProfilePanel = React.lazy(() => 
    import('./panels/ProfilePanel').then(module => ({
        default: module.ProfilePanel
    }))
);

// Custom hook with complex logic
const useLocalStorage = (key, initialValue) => {
    const [storedValue, setStoredValue] = useState(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.error(`Error reading localStorage key "${key}":`, error);
            return initialValue;
        }
    });

    const setValue = useCallback((value) => {
        try {
            const valueToStore = value instanceof Function ? value(storedValue) : value;
            setStoredValue(valueToStore);
            window.localStorage.setItem(key, JSON.stringify(valueToStore));
        } catch (error) {
            console.error(`Error setting localStorage key "${key}":`, error);
        }
    }, [key, storedValue]);

    return [storedValue, setValue];
};

// Complex functional component with render props pattern
const DataFetcher = ({ url, children, fallback = null }) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;

        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);
                
                const response = await fetch(url);
                const result = await response.json();
                
                if (!cancelled) {
                    setData(result);
                    setLoading(false);
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err);
                    setLoading(false);
                }
            }
        };

        fetchData();

        return () => {
            cancelled = true;
        };
    }, [url]);

    if (loading) return fallback || <div>Loading...</div>;
    if (error) return <div>Error: {error.message}</div>;
    
    return children({ data, loading, error });
};

// Complex arrow function with destructuring and default parameters
const processUserData = ({ 
    user = {}, 
    preferences = {}, 
    settings = {} 
} = {}) => ({
    ...user,
    fullName: `${user.firstName || ''} ${user.lastName || ''}`.trim(),
    theme: preferences.theme || settings.defaultTheme || 'light',
    notifications: {
        ...preferences.notifications,
        ...settings.notifications
    },
    isActive: user.lastLoginAt && 
               new Date() - new Date(user.lastLoginAt) < 7 * 24 * 60 * 60 * 1000
});

// Complex class component with static methods and lifecycle
class LegacyDataManager extends React.Component {
    static defaultProps = {
        refreshInterval: 30000,
        retryAttempts: 3,
        onError: () => {}
    };

    static getDerivedStateFromProps(nextProps, prevState) {
        if (nextProps.userId !== prevState.prevUserId) {
            return {
                prevUserId: nextProps.userId,
                shouldRefresh: true
            };
        }
        return null;
    }

    constructor(props) {
        super(props);
        
        this.state = {
            data: null,
            loading: false,
            error: null,
            retryCount: 0,
            prevUserId: props.userId
        };

        this.intervalId = null;
        this.abortController = null;
    }

    async componentDidMount() {
        await this.fetchData();
        this.startPeriodicRefresh();
    }

    async componentDidUpdate(prevProps, prevState) {
        if (this.state.shouldRefresh && !prevState.shouldRefresh) {
            this.setState({ shouldRefresh: false });
            await this.fetchData();
        }
    }

    componentWillUnmount() {
        this.cleanup();
    }

    cleanup = () => {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    };

    startPeriodicRefresh = () => {
        this.intervalId = setInterval(() => {
            this.fetchData(true);
        }, this.props.refreshInterval);
    };

    fetchData = async (silent = false) => {
        const { userId, onError } = this.props;
        
        if (!silent) {
            this.setState({ loading: true, error: null });
        }

        this.abortController = new AbortController();

        try {
            const response = await fetch(`/api/users/${userId}/data`, {
                signal: this.abortController.signal,
                headers: {
                    'Cache-Control': silent ? 'no-cache' : 'default'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            this.setState({
                data,
                loading: false,
                error: null,
                retryCount: 0
            });

        } catch (error) {
            if (error.name === 'AbortError') return;

            console.error('Data fetch error:', error);
            
            const newRetryCount = this.state.retryCount + 1;
            
            this.setState({
                loading: false,
                error,
                retryCount: newRetryCount
            });

            if (newRetryCount < this.props.retryAttempts) {
                setTimeout(() => this.fetchData(), 1000 * newRetryCount);
            } else {
                onError(error);
            }
        }
    };

    render() {
        const { children } = this.props;
        const { data, loading, error, retryCount } = this.state;
        
        return children({
            data,
            loading,
            error,
            retryCount,
            retry: () => this.fetchData()
        });
    }
}

// Export all components and hooks
export default UserDashboard;
export {
    AppContext,
    useAsyncOperation,
    useLocalStorage,
    SearchInput,
    DataFetcher,
    LegacyDataManager,
    withErrorBoundary,
    processUserData
};
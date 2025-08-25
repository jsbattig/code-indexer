import React, {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useContext,
    useRef,
    forwardRef,
    createContext,
    Fragment,
    Suspense,
    lazy,
    memo
} from 'react';
import { 
    createPortal,
    render 
} from 'react-dom';
import {
    BrowserRouter as Router,
    Routes,
    Route,
    Link,
    Navigate,
    useNavigate,
    useParams,
    useLocation,
    useSearchParams
} from 'react-router-dom';
import styled, { 
    ThemeProvider, 
    createGlobalStyle,
    css,
    keyframes 
} from 'styled-components';

// Type definitions for props and state
interface User {
    id: string;
    username: string;
    email: string;
    avatar?: string;
    role: 'admin' | 'user' | 'moderator';
    preferences: UserPreferences;
    createdAt: Date;
}

interface UserPreferences {
    theme: 'light' | 'dark' | 'auto';
    language: string;
    notifications: {
        email: boolean;
        push: boolean;
        sms: boolean;
    };
}

interface Post {
    id: string;
    title: string;
    content: string;
    author: User;
    tags: string[];
    createdAt: Date;
    updatedAt: Date;
    likesCount: number;
    commentsCount: number;
    isPublished: boolean;
}

interface Comment {
    id: string;
    content: string;
    author: User;
    postId: string;
    parentId?: string;
    children?: Comment[];
    createdAt: Date;
    updatedAt: Date;
    likesCount: number;
}

// Context for theme management
interface ThemeContextType {
    theme: 'light' | 'dark';
    toggleTheme: () => void;
    colors: {
        primary: string;
        secondary: string;
        background: string;
        text: string;
        border: string;
        success: string;
        error: string;
        warning: string;
    };
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const lightTheme = {
    primary: '#007bff',
    secondary: '#6c757d',
    background: '#ffffff',
    text: '#333333',
    border: '#dee2e6',
    success: '#28a745',
    error: '#dc3545',
    warning: '#ffc107'
};

const darkTheme = {
    primary: '#0d6efd',
    secondary: '#6c757d',
    background: '#1a1a1a',
    text: '#ffffff',
    border: '#333333',
    success: '#198754',
    error: '#dc3545',
    warning: '#ffc107'
};

// Custom hooks
function useTheme() {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
}

function useLocalStorage<T>(key: string, initialValue: T): [T, (value: T) => void] {
    const [storedValue, setStoredValue] = useState<T>(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.warn(`Error reading localStorage key "${key}":`, error);
            return initialValue;
        }
    });

    const setValue = useCallback((value: T) => {
        try {
            setStoredValue(value);
            window.localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.warn(`Error setting localStorage key "${key}":`, error);
        }
    }, [key]);

    return [storedValue, setValue];
}

function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);

    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedValue(value);
        }, delay);

        return () => {
            clearTimeout(handler);
        };
    }, [value, delay]);

    return debouncedValue;
}

function useApi<T>(url: string, options?: RequestInit) {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<Error | null>(null);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            
            const response = await fetch(url, options);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            setData(result);
        } catch (err) {
            setError(err instanceof Error ? err : new Error('Unknown error'));
        } finally {
            setLoading(false);
        }
    }, [url, options]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
}

function useIntersectionObserver(
    ref: React.RefObject<Element>,
    options: IntersectionObserverInit = {}
): boolean {
    const [isIntersecting, setIsIntersecting] = useState(false);

    useEffect(() => {
        const element = ref.current;
        if (!element) return;

        const observer = new IntersectionObserver(
            ([entry]) => {
                setIsIntersecting(entry.isIntersecting);
            },
            options
        );

        observer.observe(element);

        return () => {
            observer.unobserve(element);
        };
    }, [ref, options]);

    return isIntersecting;
}

// Styled Components
const fadeIn = keyframes`
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
`;

const GlobalStyle = createGlobalStyle<{ theme: ThemeContextType }>`
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        background-color: ${props => props.theme.colors.background};
        color: ${props => props.theme.colors.text};
        line-height: 1.6;
    }

    a {
        color: ${props => props.theme.colors.primary};
        text-decoration: none;
        
        &:hover {
            text-decoration: underline;
        }
    }
`;

const Container = styled.div`
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
`;

const Header = styled.header`
    background-color: ${props => props.theme.colors.background};
    border-bottom: 1px solid ${props => props.theme.colors.border};
    padding: 1rem 0;
    position: sticky;
    top: 0;
    z-index: 100;
`;

const Nav = styled.nav`
    display: flex;
    justify-content: space-between;
    align-items: center;
`;

const Logo = styled.h1`
    font-size: 1.5rem;
    font-weight: bold;
    color: ${props => props.theme.colors.primary};
`;

const NavList = styled.ul`
    display: flex;
    list-style: none;
    gap: 2rem;
    
    @media (max-width: 768px) {
        gap: 1rem;
    }
`;

const NavItem = styled.li``;

const Button = styled.button<{ 
    variant?: 'primary' | 'secondary' | 'danger' | 'success';
    size?: 'small' | 'medium' | 'large';
    fullWidth?: boolean;
}>`
    padding: ${props => {
        switch (props.size) {
            case 'small': return '0.25rem 0.5rem';
            case 'large': return '0.75rem 1.5rem';
            default: return '0.5rem 1rem';
        }
    }};
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: ${props => {
        switch (props.size) {
            case 'small': return '0.875rem';
            case 'large': return '1.125rem';
            default: return '1rem';
        }
    }};
    font-weight: 500;
    transition: all 0.2s ease;
    width: ${props => props.fullWidth ? '100%' : 'auto'};
    
    ${props => {
        const { theme } = props;
        switch (props.variant) {
            case 'primary':
                return css`
                    background-color: ${theme.colors.primary};
                    color: white;
                    
                    &:hover:not(:disabled) {
                        opacity: 0.9;
                        transform: translateY(-1px);
                    }
                `;
            case 'danger':
                return css`
                    background-color: ${theme.colors.error};
                    color: white;
                    
                    &:hover:not(:disabled) {
                        opacity: 0.9;
                    }
                `;
            case 'success':
                return css`
                    background-color: ${theme.colors.success};
                    color: white;
                    
                    &:hover:not(:disabled) {
                        opacity: 0.9;
                    }
                `;
            default:
                return css`
                    background-color: ${theme.colors.secondary};
                    color: white;
                    
                    &:hover:not(:disabled) {
                        opacity: 0.9;
                    }
                `;
        }
    }}
    
    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
    
    &:active {
        transform: translateY(0);
    }
`;

const Card = styled.div<{ elevated?: boolean }>`
    background-color: ${props => props.theme.colors.background};
    border: 1px solid ${props => props.theme.colors.border};
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    transition: all 0.2s ease;
    animation: ${fadeIn} 0.3s ease-out;
    
    ${props => props.elevated && css`
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        
        &:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
        }
    `}
`;

const Input = styled.input<{ error?: boolean }>`
    padding: 0.75rem;
    border: 1px solid ${props => props.error ? props.theme.colors.error : props.theme.colors.border};
    border-radius: 4px;
    font-size: 1rem;
    width: 100%;
    background-color: ${props => props.theme.colors.background};
    color: ${props => props.theme.colors.text};
    
    &:focus {
        outline: none;
        border-color: ${props => props.theme.colors.primary};
        box-shadow: 0 0 0 2px ${props => props.theme.colors.primary}20;
    }
`;

const TextArea = styled.textarea<{ error?: boolean }>`
    padding: 0.75rem;
    border: 1px solid ${props => props.error ? props.theme.colors.error : props.theme.colors.border};
    border-radius: 4px;
    font-size: 1rem;
    width: 100%;
    min-height: 100px;
    resize: vertical;
    background-color: ${props => props.theme.colors.background};
    color: ${props => props.theme.colors.text};
    font-family: inherit;
    
    &:focus {
        outline: none;
        border-color: ${props => props.theme.colors.primary};
        box-shadow: 0 0 0 2px ${props => props.theme.colors.primary}20;
    }
`;

const LoadingSpinner = styled.div`
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 2px solid ${props => props.theme.colors.border};
    border-radius: 50%;
    border-top-color: ${props => props.theme.colors.primary};
    animation: spin 0.8s linear infinite;
    
    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }
`;

// Component interfaces
interface HeaderProps {
    user: User | null;
    onLogout: () => void;
}

interface PostCardProps {
    post: Post;
    onLike: (postId: string) => void;
    onComment: (postId: string) => void;
    onEdit?: (postId: string) => void;
    onDelete?: (postId: string) => void;
}

interface CommentListProps {
    comments: Comment[];
    postId: string;
    onLike: (commentId: string) => void;
    onReply: (parentId: string, content: string) => void;
    onEdit: (commentId: string, content: string) => void;
    onDelete: (commentId: string) => void;
}

interface PostFormProps {
    initialData?: Partial<Post>;
    onSubmit: (data: Omit<Post, 'id' | 'author' | 'createdAt' | 'updatedAt' | 'likesCount' | 'commentsCount'>) => void;
    onCancel: () => void;
    loading?: boolean;
}

interface SearchBarProps {
    onSearch: (query: string) => void;
    placeholder?: string;
    debounceMs?: number;
}

interface PaginationProps {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    showPageNumbers?: number;
}

// Theme Provider Component
const ThemeProviderComponent: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [theme, setTheme] = useLocalStorage<'light' | 'dark'>('theme', 'light');

    const toggleTheme = useCallback(() => {
        setTheme(prev => prev === 'light' ? 'dark' : 'light');
    }, [setTheme]);

    const themeValue = useMemo<ThemeContextType>(() => ({
        theme,
        toggleTheme,
        colors: theme === 'light' ? lightTheme : darkTheme
    }), [theme, toggleTheme]);

    return (
        <ThemeContext.Provider value={themeValue}>
            <ThemeProvider theme={themeValue}>
                <GlobalStyle theme={themeValue} />
                {children}
            </ThemeProvider>
        </ThemeContext.Provider>
    );
};

// Header Component
const HeaderComponent: React.FC<HeaderProps> = ({ user, onLogout }) => {
    const { theme, toggleTheme } = useTheme();

    return (
        <Header>
            <Container>
                <Nav>
                    <Logo>My Blog</Logo>
                    <NavList>
                        <NavItem>
                            <Link to="/">Home</Link>
                        </NavItem>
                        <NavItem>
                            <Link to="/posts">Posts</Link>
                        </NavItem>
                        {user ? (
                            <>
                                <NavItem>
                                    <Link to="/create">Create Post</Link>
                                </NavItem>
                                <NavItem>
                                    <Link to="/profile">Profile</Link>
                                </NavItem>
                                <NavItem>
                                    <Button size="small" onClick={onLogout}>
                                        Logout
                                    </Button>
                                </NavItem>
                            </>
                        ) : (
                            <>
                                <NavItem>
                                    <Link to="/login">Login</Link>
                                </NavItem>
                                <NavItem>
                                    <Link to="/register">Register</Link>
                                </NavItem>
                            </>
                        )}
                        <NavItem>
                            <Button size="small" onClick={toggleTheme}>
                                {theme === 'light' ? '🌙' : '☀️'}
                            </Button>
                        </NavItem>
                    </NavList>
                </Nav>
            </Container>
        </Header>
    );
};

// Post Card Component
const PostCard: React.FC<PostCardProps> = memo(({ 
    post, 
    onLike, 
    onComment, 
    onEdit, 
    onDelete 
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const { theme } = useTheme();

    const toggleExpanded = useCallback(() => {
        setIsExpanded(prev => !prev);
    }, []);

    const handleLike = useCallback(() => {
        onLike(post.id);
    }, [onLike, post.id]);

    const handleComment = useCallback(() => {
        onComment(post.id);
    }, [onComment, post.id]);

    const handleEdit = useCallback(() => {
        onEdit?.(post.id);
    }, [onEdit, post.id]);

    const handleDelete = useCallback(() => {
        onDelete?.(post.id);
    }, [onDelete, post.id]);

    const truncatedContent = useMemo(() => {
        return post.content.length > 200 
            ? post.content.substring(0, 200) + '...'
            : post.content;
    }, [post.content]);

    return (
        <Card elevated>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div>
                    <h2 style={{ marginBottom: '0.5rem', color: theme.colors.text }}>
                        {post.title}
                    </h2>
                    <div style={{ fontSize: '0.875rem', color: theme.colors.secondary, marginBottom: '1rem' }}>
                        By {post.author.username} • {post.createdAt.toLocaleDateString()}
                        {post.createdAt.getTime() !== post.updatedAt.getTime() && (
                            <span> • Updated {post.updatedAt.toLocaleDateString()}</span>
                        )}
                    </div>
                </div>
                {(onEdit || onDelete) && (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        {onEdit && (
                            <Button size="small" variant="secondary" onClick={handleEdit}>
                                Edit
                            </Button>
                        )}
                        {onDelete && (
                            <Button size="small" variant="danger" onClick={handleDelete}>
                                Delete
                            </Button>
                        )}
                    </div>
                )}
            </div>

            <div style={{ marginBottom: '1rem' }}>
                {post.tags.map(tag => (
                    <span 
                        key={tag}
                        style={{
                            display: 'inline-block',
                            background: theme.colors.primary + '20',
                            color: theme.colors.primary,
                            padding: '0.25rem 0.5rem',
                            borderRadius: '12px',
                            fontSize: '0.75rem',
                            marginRight: '0.5rem',
                            marginBottom: '0.25rem'
                        }}
                    >
                        #{tag}
                    </span>
                ))}
            </div>

            <p style={{ marginBottom: '1rem', lineHeight: '1.6' }}>
                {isExpanded ? post.content : truncatedContent}
                {post.content.length > 200 && (
                    <button
                        onClick={toggleExpanded}
                        style={{
                            background: 'none',
                            border: 'none',
                            color: theme.colors.primary,
                            cursor: 'pointer',
                            marginLeft: '0.5rem'
                        }}
                    >
                        {isExpanded ? 'Show less' : 'Read more'}
                    </button>
                )}
            </p>

            <div style={{ 
                display: 'flex', 
                gap: '1rem', 
                alignItems: 'center',
                paddingTop: '1rem',
                borderTop: `1px solid ${theme.colors.border}`
            }}>
                <Button size="small" onClick={handleLike}>
                    👍 {post.likesCount}
                </Button>
                <Button size="small" variant="secondary" onClick={handleComment}>
                    💬 {post.commentsCount}
                </Button>
                {!post.isPublished && (
                    <span style={{ 
                        color: theme.colors.warning, 
                        fontSize: '0.875rem',
                        marginLeft: 'auto'
                    }}>
                        Draft
                    </span>
                )}
            </div>
        </Card>
    );
});

PostCard.displayName = 'PostCard';

// Comment Component with recursive rendering
const CommentComponent: React.FC<{
    comment: Comment;
    depth?: number;
    onLike: (commentId: string) => void;
    onReply: (parentId: string, content: string) => void;
    onEdit: (commentId: string, content: string) => void;
    onDelete: (commentId: string) => void;
}> = ({ comment, depth = 0, onLike, onReply, onEdit, onDelete }) => {
    const [isReplying, setIsReplying] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [replyContent, setReplyContent] = useState('');
    const [editContent, setEditContent] = useState(comment.content);
    const { theme } = useTheme();

    const handleLike = useCallback(() => {
        onLike(comment.id);
    }, [onLike, comment.id]);

    const handleReplySubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        if (replyContent.trim()) {
            await onReply(comment.id, replyContent.trim());
            setReplyContent('');
            setIsReplying(false);
        }
    }, [onReply, comment.id, replyContent]);

    const handleEditSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        if (editContent.trim() && editContent !== comment.content) {
            await onEdit(comment.id, editContent.trim());
            setIsEditing(false);
        }
    }, [onEdit, comment.id, editContent, comment.content]);

    const handleDelete = useCallback(() => {
        if (window.confirm('Are you sure you want to delete this comment?')) {
            onDelete(comment.id);
        }
    }, [onDelete, comment.id]);

    return (
        <div style={{ 
            marginLeft: `${depth * 2}rem`,
            borderLeft: depth > 0 ? `2px solid ${theme.colors.border}` : 'none',
            paddingLeft: depth > 0 ? '1rem' : '0',
            marginBottom: '1rem'
        }}>
            <Card>
                <div style={{ fontSize: '0.875rem', color: theme.colors.secondary, marginBottom: '0.5rem' }}>
                    {comment.author.username} • {comment.createdAt.toLocaleDateString()}
                    {comment.createdAt.getTime() !== comment.updatedAt.getTime() && ' • edited'}
                </div>

                {isEditing ? (
                    <form onSubmit={handleEditSubmit} style={{ marginBottom: '1rem' }}>
                        <TextArea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            rows={3}
                        />
                        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                            <Button type="submit" size="small" variant="primary">
                                Save
                            </Button>
                            <Button 
                                type="button" 
                                size="small" 
                                variant="secondary"
                                onClick={() => {
                                    setIsEditing(false);
                                    setEditContent(comment.content);
                                }}
                            >
                                Cancel
                            </Button>
                        </div>
                    </form>
                ) : (
                    <p style={{ marginBottom: '1rem', lineHeight: '1.6' }}>
                        {comment.content}
                    </p>
                )}

                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <Button size="small" onClick={handleLike}>
                        👍 {comment.likesCount}
                    </Button>
                    {depth < 3 && (
                        <Button 
                            size="small" 
                            variant="secondary"
                            onClick={() => setIsReplying(!isReplying)}
                        >
                            Reply
                        </Button>
                    )}
                    <Button 
                        size="small" 
                        variant="secondary"
                        onClick={() => setIsEditing(!isEditing)}
                    >
                        Edit
                    </Button>
                    <Button 
                        size="small" 
                        variant="danger"
                        onClick={handleDelete}
                    >
                        Delete
                    </Button>
                </div>

                {isReplying && (
                    <form onSubmit={handleReplySubmit} style={{ marginTop: '1rem' }}>
                        <TextArea
                            value={replyContent}
                            onChange={(e) => setReplyContent(e.target.value)}
                            placeholder="Write your reply..."
                            rows={3}
                        />
                        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                            <Button type="submit" size="small" variant="primary">
                                Reply
                            </Button>
                            <Button 
                                type="button" 
                                size="small" 
                                variant="secondary"
                                onClick={() => {
                                    setIsReplying(false);
                                    setReplyContent('');
                                }}
                            >
                                Cancel
                            </Button>
                        </div>
                    </form>
                )}
            </Card>

            {comment.children && comment.children.map(child => (
                <CommentComponent
                    key={child.id}
                    comment={child}
                    depth={depth + 1}
                    onLike={onLike}
                    onReply={onReply}
                    onEdit={onEdit}
                    onDelete={onDelete}
                />
            ))}
        </div>
    );
};

// Search Bar Component
const SearchBar: React.FC<SearchBarProps> = ({ 
    onSearch, 
    placeholder = "Search posts...", 
    debounceMs = 300 
}) => {
    const [query, setQuery] = useState('');
    const debouncedQuery = useDebounce(query, debounceMs);

    useEffect(() => {
        onSearch(debouncedQuery);
    }, [debouncedQuery, onSearch]);

    return (
        <div style={{ marginBottom: '2rem' }}>
            <Input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
            />
        </div>
    );
};

// Pagination Component
const Pagination: React.FC<PaginationProps> = ({
    currentPage,
    totalPages,
    onPageChange,
    showPageNumbers = 5
}) => {
    const { theme } = useTheme();

    const getVisiblePages = useMemo(() => {
        const pages: number[] = [];
        const halfShow = Math.floor(showPageNumbers / 2);
        
        let start = Math.max(1, currentPage - halfShow);
        let end = Math.min(totalPages, currentPage + halfShow);
        
        if (end - start + 1 < showPageNumbers) {
            if (start === 1) {
                end = Math.min(totalPages, start + showPageNumbers - 1);
            } else {
                start = Math.max(1, end - showPageNumbers + 1);
            }
        }
        
        for (let i = start; i <= end; i++) {
            pages.push(i);
        }
        
        return pages;
    }, [currentPage, totalPages, showPageNumbers]);

    if (totalPages <= 1) return null;

    return (
        <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            gap: '0.5rem', 
            marginTop: '2rem' 
        }}>
            <Button
                size="small"
                variant="secondary"
                disabled={currentPage === 1}
                onClick={() => onPageChange(currentPage - 1)}
            >
                Previous
            </Button>
            
            {getVisiblePages[0] > 1 && (
                <>
                    <Button
                        size="small"
                        variant="secondary"
                        onClick={() => onPageChange(1)}
                    >
                        1
                    </Button>
                    {getVisiblePages[0] > 2 && (
                        <span style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            padding: '0 0.5rem',
                            color: theme.colors.secondary
                        }}>
                            ...
                        </span>
                    )}
                </>
            )}
            
            {getVisiblePages.map(page => (
                <Button
                    key={page}
                    size="small"
                    variant={page === currentPage ? "primary" : "secondary"}
                    onClick={() => onPageChange(page)}
                >
                    {page}
                </Button>
            ))}
            
            {getVisiblePages[getVisiblePages.length - 1] < totalPages && (
                <>
                    {getVisiblePages[getVisiblePages.length - 1] < totalPages - 1 && (
                        <span style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            padding: '0 0.5rem',
                            color: theme.colors.secondary
                        }}>
                            ...
                        </span>
                    )}
                    <Button
                        size="small"
                        variant="secondary"
                        onClick={() => onPageChange(totalPages)}
                    >
                        {totalPages}
                    </Button>
                </>
            )}
            
            <Button
                size="small"
                variant="secondary"
                disabled={currentPage === totalPages}
                onClick={() => onPageChange(currentPage + 1)}
            >
                Next
            </Button>
        </div>
    );
};

// Post Form Component
const PostForm: React.FC<PostFormProps> = ({ 
    initialData, 
    onSubmit, 
    onCancel, 
    loading = false 
}) => {
    const [title, setTitle] = useState(initialData?.title || '');
    const [content, setContent] = useState(initialData?.content || '');
    const [tags, setTags] = useState(initialData?.tags?.join(', ') || '');
    const [isPublished, setIsPublished] = useState(initialData?.isPublished || false);
    
    const [errors, setErrors] = useState<{ [key: string]: string }>({});
    
    const validate = useCallback(() => {
        const newErrors: { [key: string]: string } = {};
        
        if (!title.trim()) {
            newErrors.title = 'Title is required';
        } else if (title.length < 3) {
            newErrors.title = 'Title must be at least 3 characters';
        }
        
        if (!content.trim()) {
            newErrors.content = 'Content is required';
        } else if (content.length < 10) {
            newErrors.content = 'Content must be at least 10 characters';
        }
        
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    }, [title, content]);

    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        
        if (!validate()) {
            return;
        }

        const tagArray = tags
            .split(',')
            .map(tag => tag.trim())
            .filter(tag => tag.length > 0);

        onSubmit({
            title: title.trim(),
            content: content.trim(),
            tags: tagArray,
            isPublished
        });
    }, [title, content, tags, isPublished, onSubmit, validate]);

    return (
        <Card>
            <form onSubmit={handleSubmit}>
                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
                        Title *
                    </label>
                    <Input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        error={!!errors.title}
                        disabled={loading}
                        placeholder="Enter post title"
                    />
                    {errors.title && (
                        <div style={{ color: 'red', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                            {errors.title}
                        </div>
                    )}
                </div>

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
                        Content *
                    </label>
                    <TextArea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        error={!!errors.content}
                        disabled={loading}
                        placeholder="Write your post content here..."
                        rows={10}
                    />
                    {errors.content && (
                        <div style={{ color: 'red', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                            {errors.content}
                        </div>
                    )}
                </div>

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
                        Tags (comma separated)
                    </label>
                    <Input
                        type="text"
                        value={tags}
                        onChange={(e) => setTags(e.target.value)}
                        disabled={loading}
                        placeholder="react, typescript, tutorial"
                    />
                </div>

                <div style={{ marginBottom: '2rem' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                        <input
                            type="checkbox"
                            checked={isPublished}
                            onChange={(e) => setIsPublished(e.target.checked)}
                            disabled={loading}
                        />
                        <span style={{ fontWeight: 'bold' }}>Publish immediately</span>
                    </label>
                </div>

                <div style={{ display: 'flex', gap: '1rem' }}>
                    <Button
                        type="submit"
                        variant="primary"
                        disabled={loading}
                    >
                        {loading ? (
                            <>
                                <LoadingSpinner /> Saving...
                            </>
                        ) : (
                            initialData ? 'Update Post' : 'Create Post'
                        )}
                    </Button>
                    <Button
                        type="button"
                        variant="secondary"
                        onClick={onCancel}
                        disabled={loading}
                    >
                        Cancel
                    </Button>
                </div>
            </form>
        </Card>
    );
};

// Posts List Component with Infinite Scroll
const PostsList: React.FC<{
    posts: Post[];
    user: User | null;
    onLoadMore: () => void;
    hasMore: boolean;
    loading: boolean;
    onLike: (postId: string) => void;
    onComment: (postId: string) => void;
    onEdit: (postId: string) => void;
    onDelete: (postId: string) => void;
}> = ({ 
    posts, 
    user, 
    onLoadMore, 
    hasMore, 
    loading, 
    onLike, 
    onComment, 
    onEdit, 
    onDelete 
}) => {
    const loadMoreRef = useRef<HTMLDivElement>(null);
    const isLoadMoreVisible = useIntersectionObserver(loadMoreRef, {
        threshold: 0.1
    });

    useEffect(() => {
        if (isLoadMoreVisible && hasMore && !loading) {
            onLoadMore();
        }
    }, [isLoadMoreVisible, hasMore, loading, onLoadMore]);

    return (
        <div>
            {posts.map(post => (
                <PostCard
                    key={post.id}
                    post={post}
                    onLike={onLike}
                    onComment={onComment}
                    onEdit={user?.id === post.author.id ? onEdit : undefined}
                    onDelete={user?.id === post.author.id ? onDelete : undefined}
                />
            ))}
            
            {hasMore && (
                <div ref={loadMoreRef} style={{ padding: '2rem', textAlign: 'center' }}>
                    {loading ? <LoadingSpinner /> : 'Load more posts...'}
                </div>
            )}
        </div>
    );
};

// Main App Component
const App: React.FC = () => {
    return (
        <ThemeProviderComponent>
            <Router>
                <div style={{ minHeight: '100vh' }}>
                    <Suspense fallback={
                        <div style={{ 
                            display: 'flex', 
                            justifyContent: 'center', 
                            alignItems: 'center', 
                            height: '100vh' 
                        }}>
                            <LoadingSpinner />
                        </div>
                    }>
                        <AppContent />
                    </Suspense>
                </div>
            </Router>
        </ThemeProviderComponent>
    );
};

// App Content Component
const AppContent: React.FC = () => {
    const [user, setUser] = useState<User | null>(null);
    
    // Mock user for demonstration
    useEffect(() => {
        // Simulate user authentication
        setUser({
            id: '1',
            username: 'johndoe',
            email: 'john@example.com',
            role: 'user',
            preferences: {
                theme: 'light',
                language: 'en',
                notifications: {
                    email: true,
                    push: false,
                    sms: false
                }
            },
            createdAt: new Date()
        });
    }, []);

    const handleLogout = useCallback(() => {
        setUser(null);
    }, []);

    return (
        <>
            <HeaderComponent user={user} onLogout={handleLogout} />
            <Container>
                <main style={{ padding: '2rem 0' }}>
                    <Routes>
                        <Route path="/" element={<HomePage user={user} />} />
                        <Route path="/posts" element={<PostsPage user={user} />} />
                        <Route path="/post/:id" element={<PostDetailPage user={user} />} />
                        <Route path="/create" element={
                            user ? <CreatePostPage /> : <Navigate to="/login" />
                        } />
                        <Route path="/edit/:id" element={
                            user ? <EditPostPage /> : <Navigate to="/login" />
                        } />
                        <Route path="/profile" element={
                            user ? <ProfilePage user={user} /> : <Navigate to="/login" />
                        } />
                        <Route path="/login" element={<LoginPage />} />
                        <Route path="/register" element={<RegisterPage />} />
                    </Routes>
                </main>
            </Container>
        </>
    );
};

// Lazy loaded page components
const HomePage = lazy(() => import('./pages/HomePage'));
const PostsPage = lazy(() => import('./pages/PostsPage'));
const PostDetailPage = lazy(() => import('./pages/PostDetailPage'));
const CreatePostPage = lazy(() => import('./pages/CreatePostPage'));
const EditPostPage = lazy(() => import('./pages/EditPostPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const RegisterPage = lazy(() => import('./pages/RegisterPage'));

export default App;

// Export components and types for reuse
export {
    ThemeProviderComponent,
    HeaderComponent,
    PostCard,
    CommentComponent,
    SearchBar,
    Pagination,
    PostForm,
    PostsList,
    LoadingSpinner,
    Button,
    Input,
    TextArea,
    Card,
    Container
};

export type {
    User,
    Post,
    Comment,
    UserPreferences,
    PostCardProps,
    CommentListProps,
    PostFormProps,
    SearchBarProps,
    PaginationProps,
    HeaderProps
};
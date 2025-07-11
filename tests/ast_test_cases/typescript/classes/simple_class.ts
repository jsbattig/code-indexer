class UserService {
    private users: User[] = [];

    constructor(private readonly apiClient: ApiClient) {}

    async findUser(id: number): Promise<User | null> {
        return this.users.find(user => user.id === id) || null;
    }

    addUser(user: User): void {
        this.users.push(user);
    }
}

enum Color {
    Red = "red",
    Green = "green",
    Blue = "blue"
}

interface User {
    id: number;
    name: string;
    email?: string;
}
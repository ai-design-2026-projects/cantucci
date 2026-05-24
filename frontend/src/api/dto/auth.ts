export interface User {
    id: string
    email: string
    role: string
}

export interface LoginResponse {
    token: string
    user: User
}

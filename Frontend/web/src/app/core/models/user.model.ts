export type UserRole = 'ADMIN' | 'AGENT';

export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  role: UserRole;
  avatar?: string;
  isActive: boolean;
  resetPasswordRequested?: boolean;
}

export interface AuthResponse {
  token: string;
  user: User;
}

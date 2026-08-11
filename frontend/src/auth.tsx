import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { clearSession, getStoredUser, login as apiLogin } from "./api";
import type { User } from "./api";

interface AuthValue {
  user: User | null;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue>({
  user: null,
  signIn: async () => {
    throw new Error("no provider");
  },
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(getStoredUser());

  const value = useMemo<AuthValue>(
    () => ({
      user,
      signIn: async (email, password) => {
        const next = await apiLogin(email, password);
        setUser(next);
        return next;
      },
      signOut: () => {
        clearSession();
        setUser(null);
      },
    }),
    [user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import * as coreClient from "../api/coreClient";
import { User } from "../api/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function restoreSession() {
      const accessToken = coreClient.getAccessToken();
      const refreshToken = coreClient.getRefreshToken();

      if (!accessToken || !refreshToken) {
        setLoading(false);
        return;
      }

      try {
        setUser(await coreClient.me(accessToken));
      } catch {
        try {
          const tokens = await coreClient.refresh(refreshToken);
          coreClient.setTokens(tokens.access_token, tokens.refresh_token);
          setUser(await coreClient.me(tokens.access_token));
        } catch {
          coreClient.clearTokens();
        }
      } finally {
        setLoading(false);
      }
    }

    restoreSession();
  }, []);

  async function login(email: string, password: string) {
    const tokens = await coreClient.login({ email, password });
    coreClient.setTokens(tokens.access_token, tokens.refresh_token);
    setUser(await coreClient.me(tokens.access_token));
  }

  async function register(name: string, email: string, password: string) {
    await coreClient.register({ name, email, password });
    await login(email, password);
  }

  function logout() {
    coreClient.clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

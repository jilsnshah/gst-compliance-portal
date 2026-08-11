import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { isCA } from "../api";

const TEST_ACCOUNTS = [
  { email: "admin@test.com", label: "CA Admin / Partner — sees every client" },
  { email: "staff@test.com", label: "CA Employee — sees assigned clients only" },
  { email: "client@test.com", label: "Client — ABC Enterprises" },
  { email: "client2@test.com", label: "Client — XYZ Traders" },
];

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("staff@test.com");
  const [password, setPassword] = useState("test123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await signIn(email, password);
      navigate(isCA(user.role) ? "/ca" : "/portal", { replace: true });
    } catch (err: any) {
      setError(err.message ?? "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1 style={{ marginBottom: 2 }}>GST Compliance Portal</h1>
        <p className="sub" style={{ marginTop: 0, marginBottom: 20 }}>
          Monthly GST workflow for the CA firm and its clients.
        </p>

        {error && <div className="error">{error}</div>}

        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </div>
        <div className="field">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        <button className="primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <div className="test-accounts">
          Dev-stage test accounts (password <code>test123</code>). Google sign-in arrives in Stage 2.
          {TEST_ACCOUNTS.map((acc) => (
            <button key={acc.email} type="button" onClick={() => { setEmail(acc.email); setPassword("test123"); }}>
              <strong>{acc.email}</strong>
              <br />
              {acc.label}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}

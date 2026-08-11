import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { get, isCA } from "./api";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import ClientDashboard from "./pages/ClientDashboard";
import CaDashboard from "./pages/CaDashboard";
import CaseWorkspace from "./pages/CaseWorkspace";
import ComplianceGrid from "./pages/ComplianceGrid";
import Clients from "./pages/Clients";
import FileProfile from "./pages/FileProfile";
import TeamActivity from "./pages/TeamActivity";
import AuditTrail from "./pages/AuditTrail";
import Inbox from "./pages/Messages";
import ClientMonth from "./pages/ClientMonth";

function Shell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) return;
    get("/api/notifications?unread_only=true&limit=1")
      .then((r) => setUnread(r.unread_count))
      .catch(() => {});
  }, [user, location.pathname]);

  if (!user) return <Navigate to="/login" replace />;
  const ca = isCA(user.role);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          GST Compliance
          <small>{ca ? "CA / Admin portal" : "Client portal"}</small>
        </div>
        <nav>
          {ca ? (
            <>
              <NavLink to="/ca" end>Today's work</NavLink>
              <NavLink to="/ca/grid">Compliance grid</NavLink>
              <NavLink to="/ca/clients">Clients &amp; files</NavLink>
              <NavLink to="/messages">
                Needs attention
                {unread > 0 && <span className="badge-count">{unread}</span>}
              </NavLink>
              <NavLink to="/ca/team">Team activity</NavLink>
              <NavLink to="/ca/audit">Audit trail</NavLink>
            </>
          ) : (
            <>
              <NavLink to="/portal" end>My GST months</NavLink>
              <NavLink to="/messages">
                Needs attention
                {unread > 0 && <span className="badge-count">{unread}</span>}
              </NavLink>
            </>
          )}
        </nav>
        <div className="spacer" />
        <div className="who">
          <strong>{user.full_name}</strong>
          {user.email}
          <div style={{ marginTop: 4 }}>{user.role.replace(/_/g, " ")}</div>
          <button
            className="ghost"
            style={{ padding: "4px 0", marginTop: 8 }}
            onClick={() => {
              signOut();
              navigate("/login", { replace: true });
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  const { user } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={isCA(user.role) ? "/ca" : "/portal"} replace /> : <Login />} />
      <Route path="/" element={<Navigate to={user ? (isCA(user.role) ? "/ca" : "/portal") : "/login"} replace />} />
      <Route path="/portal" element={<Shell><ClientDashboard /></Shell>} />
      <Route path="/ca" element={<Shell><CaDashboard /></Shell>} />
      <Route path="/ca/grid" element={<Shell><ComplianceGrid /></Shell>} />
      <Route path="/ca/clients" element={<Shell><Clients /></Shell>} />
      <Route path="/ca/files/:entityId" element={<Shell><FileProfile /></Shell>} />
      <Route path="/ca/team" element={<Shell><TeamActivity /></Shell>} />
      <Route path="/ca/audit" element={<Shell><AuditTrail /></Shell>} />
      <Route path="/messages" element={<Shell><Inbox /></Shell>} />
      {/* Same URL, two experiences: the client gets the stepper, the CA the workspace. */}
      <Route
        path="/cases/:caseId"
        element={<Shell>{user && isCA(user.role) ? <CaseWorkspace /> : <ClientMonth />}</Shell>}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

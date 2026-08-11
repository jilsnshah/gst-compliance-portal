const BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8010";
// Sessions live in sessionStorage, not localStorage, so each browser tab holds
// its own login. That is what lets you drive the CA portal in one tab and the
// client portal in another without one signing the other out.
const TOKEN_KEY = "gst_token";
const USER_KEY = "gst_user";
const store = () => window.sessionStorage;

export type Role = "CLIENT" | "CA_EMPLOYEE" | "CA_ADMIN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  employee_id: number | null;
  client_ids: number[];
}

export interface ReturnItem {
  id: number;
  case_id: number;
  return_type: "GSTR1" | "PR_RECON" | "GSTR3B";
  return_label: string;
  status: string;
  status_label: string;
  client_status: string;
  client_status_label: string;
  progress: number;
  due_date: string | null;
  assigned_employee_id: number | null;
  review_started_at: string | null;
  review_started_by: string | null;
  allowed_next: string[];
  updated_at: string;
  is_terminal: boolean;
  waiting_on: "CLIENT" | "CA" | "NOBODY";
  has_open_query: boolean;
  blocked_reason: string | null;
  internal_status?: string;
}

export interface CaseSummary {
  id: number;
  status: string;
  client: { id: number; name: string; code: string };
  entity: { id: number; legal_name: string; trade_name: string | null; file_number: string };
  gstin: string;
  period: { id: number; code: string; label: string; gstr1_due_date: string | null; gstr3b_due_date: string | null };
  returns: ReturnItem[];
  overall_progress?: number;
  documents?: number | any[];
  open_queries?: number;
  action_required?: string[];
  reconciliation?: { match_rate: number; action_required: number; total: number } | null;
}

export function getToken() {
  return store().getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  const raw = store().getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function storeSession(token: string, user: User) {
  store().setItem(TOKEN_KEY, token);
  store().setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  store().removeItem(TOKEN_KEY);
  store().removeItem(USER_KEY);
  // Clear any session left over from when these lived in localStorage.
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle(res: Response) {
  if (res.status === 204) return null;
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body?.detail ?? body ?? res.statusText;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api(path: string, options: RequestInit = {}) {
  const res = await fetch(BASE + path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers ?? {}) },
  });
  return handle(res);
}

export function get(path: string) {
  return api(path);
}

export function post(path: string, body?: unknown) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function patch(path: string, body: unknown) {
  return api(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function upload(path: string, form: FormData) {
  return api(path, { method: "POST", body: form });
}

export async function download(path: string, filename: string) {
  const res = await fetch(BASE + path, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function login(email: string, password: string) {
  const res = await fetch(BASE + "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await handle(res);
  storeSession(data.access_token, data.user);
  return data.user as User;
}

export const isCA = (role?: Role) => role === "CA_EMPLOYEE" || role === "CA_ADMIN";

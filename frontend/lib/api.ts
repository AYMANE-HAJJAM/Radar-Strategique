import type {User} from "@/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000").replace(/\/$/, "");
let csrfToken = "";

export class ApiError extends Error { constructor(public code:string, message:string, public status:number){super(message);} }

export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${API_URL}/api${path}`, {credentials:"include", ...init, signal:controller.signal,
      headers:{"Content-Type":"application/json", ...(csrfToken ? {"X-CSRF-Token":csrfToken}:{}), ...init.headers}});
    if (response.status === 204) return undefined as T;
    const data = await response.json();
    if (!response.ok) throw new ApiError(data.error?.code || "REQUEST_FAILED", data.error?.message || "Erreur serveur", response.status);
    if (typeof data.csrf_token === "string") csrfToken = data.csrf_token;
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new ApiError("TIMEOUT", "Le serveur met du temps à répondre. Réessayez dans un instant.", 408);
    throw error;
  } finally { clearTimeout(timeout); }
}

export const auth = {
  access:(access_code:string)=>api<{user:User;csrf_token:string}>("/auth/access",{method:"POST",body:JSON.stringify({access_code})}),
  me:()=>api<{user:User;csrf_token:string}>("/auth/me"),
  logout:()=>api<void>("/auth/logout",{method:"POST"})
};

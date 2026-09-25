import type {User} from "@/types";

// Same-origin only. next.config.ts rewrites /api to the backend.
let csrfToken = "";

export class ApiError extends Error { constructor(public code:string, message:string, public status:number){super(message);} }

export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const headers = new Headers(init.headers);
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
    const response = await fetch(`/api${path}`, {...init, credentials:"include", signal:controller.signal, headers});
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

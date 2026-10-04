/** claude.ai Artifact build: hash routing, no file downloads (the viewer blocks them). */
export const ARTIFACT = import.meta.env.VITE_ARTIFACT === "1";
/** Static hosting without the local proxy (Artifact or Azure Static Web Apps): the LLM routes are off. */
export const NO_PROXY = ARTIFACT || import.meta.env.VITE_NO_PROXY === "1";
/**
 * Base URL of the comparator API (Azure Function or the local Python server). "" = same origin (/api, local dev and presenter);
 * null = no backend (public static build without VITE_API_BASE): every live control degrades to replay or a disabled state.
 */
export const API_BASE: string | null = import.meta.env.VITE_API_BASE != null && import.meta.env.VITE_API_BASE !== ""
  ? String(import.meta.env.VITE_API_BASE).replace(/\/$/, "")
  : NO_PROXY ? null : "";

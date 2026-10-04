/** claude.ai Artifact build: hash routing, no file downloads (the viewer blocks them). */
export const ARTIFACT = import.meta.env.VITE_ARTIFACT === "1";
/** Static hosting without the local proxy (Artifact or Azure Static Web Apps): the LLM routes are off. */
export const NO_PROXY = ARTIFACT || import.meta.env.VITE_NO_PROXY === "1";

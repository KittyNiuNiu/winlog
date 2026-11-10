// Vite build-time variables used by the API client. Vite reads them from the
// repository-root .env (envDir in vite.config.ts) or from the build environment.
interface ImportMetaEnv {
  /** Base URL of the backend API, for example http://localhost:8000. */
  readonly VITE_API_BASE_URL?: string
}

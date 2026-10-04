import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { applyTheme, useSettings } from "./data/store";

applyTheme(useSettings.getState().theme);
// A hosting viewer may set data-theme on the root element (explicit light/dark); follow it while the app setting is "system".
new MutationObserver(() => applyTheme(useSettings.getState().theme)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);

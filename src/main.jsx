import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { reportError } from "./utils/report";
import "../styles.css";
import "../admin.css";

window.addEventListener("error", (event) => {
  reportError("window.error", event.error || new Error(`${event.message} (${event.filename}:${event.lineno})`));
});

window.addEventListener("unhandledrejection", (event) => {
  reportError("unhandledrejection", event.reason);
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ErrorBoundary name="app">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>
);

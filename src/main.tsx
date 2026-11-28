import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { applyMotionLevel, readMotionLevel } from "./lib/motion";
import { readTheme } from "./lib/theme";
import "./styles/global.css";

applyMotionLevel(readMotionLevel());
document.documentElement.dataset.theme = readTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

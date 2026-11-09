import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { BASE, installBase } from "./lib/base";

installBase();
import "./styles.css";
import "./app.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={BASE || undefined}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

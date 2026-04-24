import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import App from "./App";
import DebateDetail from "./pages/DebateDetail";
import Debates from "./pages/Debates";
import Observatory from "./pages/Observatory";
import Payout from "./pages/Payout";
import Shapley from "./pages/Shapley";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchInterval: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<App />}>
            <Route path="/" element={<Observatory />} />
            <Route path="/debates" element={<Debates />} />
            <Route path="/debates/:debateId" element={<DebateDetail />} />
            <Route path="/shapley" element={<Shapley />} />
            <Route path="/payout" element={<Payout />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);

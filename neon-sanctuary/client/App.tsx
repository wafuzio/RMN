import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { createRoot } from "react-dom/client";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import { API_BASE } from "@/lib/api";
import Index from "./pages/Index";
import Brands from "./pages/Brands";
import VideoOverlayTest from "./pages/VideoOverlayTest";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

// Prime ngrok cookie on app boot to prevent interstitial on image requests
function PrimeNgrokCookie() {
  useEffect(() => {
    // This sets ngrok's skip cookie so subsequent <img> requests won't get the interstitial
    fetch(`${API_BASE}/api/ping`, {
      headers: { 'ngrok-skip-browser-warning': 'true' },
      credentials: 'include', // let ngrok set its cookie
      mode: 'cors',
    }).catch(() => {});
  }, []);
  return null;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <PrimeNgrokCookie />
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/brands" element={<Brands />} />
          <Route path="/video-overlay-test" element={<VideoOverlayTest />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

createRoot(document.getElementById("root")!).render(<App />);

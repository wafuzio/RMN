import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { createRoot } from "react-dom/client";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import { API_BASE } from "@/lib/api";
import { PerformanceCard } from "@/components/PerformanceCard";
import Index from "./pages/Index";
import Brands from "./pages/Brands";
import RetailSnapshot from "./pages/RetailSnapshot";
import Gopuff from "./pages/Gopuff";
import { TemporalVisualMapPage } from "./pages/TemporalVisualMapPage";
import VideoOverlayTest from "./pages/VideoOverlayTest";
import Experiments from "./pages/Experiments";
import ReviewQueue from "./pages/ReviewQueue";
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
          <Route path="/retail-snapshot" element={<RetailSnapshot />} />
          <Route path="/gopuff" element={<Gopuff />} />
          <Route path="/temporal-visual-map" element={<TemporalVisualMapPage />} />
          <Route path="/experiments" element={<Experiments />} />
          <Route path="/video-overlay-test" element={<VideoOverlayTest />} />
          <Route path="/review-queue" element={<ReviewQueue />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
      {/* Global performance monitoring card (visible with ?devperf=1) */}
      <PerformanceCard />
    </TooltipProvider>
  </QueryClientProvider>
);

createRoot(document.getElementById("root")!).render(<App />);

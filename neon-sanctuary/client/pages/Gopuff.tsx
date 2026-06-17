import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import GaleLogo from "../../../web/assets/logos/GALE.svg";

const BACKDROP_URL = "https://cdn.builder.io/api/v1/image/assets%2F856cf3d807e24856a8ddedcb12249a98%2F39b2908acfb84ba8a6bbc813e433343c?format=webp&width=800&height=1200";

export default function Gopuff() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      {/* Mockup container - sized to image proportions */}
      <div className="relative w-full max-w-md scale-150 origin-top">
        {/* Backdrop Image */}
        <img
          src={BACKDROP_URL}
          alt="GoPuff Mockup"
          className="w-full h-auto"
        />

        {/* Overlay layer for elements (z-index positioning) */}
        <div className="absolute inset-0 flex flex-col">
          {/* Add your layered elements here - use absolute positioning */}
        </div>
      </div>

      {/* Controls bar (outside mockup) */}
      <div className="fixed top-4 left-4 right-4 flex gap-2">
        <Button
          variant="outline"
          onClick={() => navigate("/")}
          size="sm"
        >
          Back to Dashboard
        </Button>
      </div>
    </div>
  );
}

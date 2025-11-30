import { useEffect, useRef, useState } from "react";
import { Slider } from "@/components/ui/slider";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

export default function KeywordWindTunnel() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [intensity, setIntensity] = useState(50);
  const particlesRef = useRef<Particle[]>([]);
  const timeRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    canvas.width = width;
    canvas.height = height;

    const particles = particlesRef.current;
    const barriers = [
      { x: width * 0.25, y: height * 0.3, w: 15, h: 80 },
      { x: width * 0.5, y: height * 0.2, w: 15, h: 120 },
      { x: width * 0.75, y: height * 0.4, w: 15, h: 90 },
    ];

    const animate = () => {
      timeRef.current++;
      const pressure = intensity / 100;

      // Clean background
      ctx.fillStyle = "rgba(15, 23, 42, 0.2)";
      ctx.fillRect(0, 0, width, height);

      // Emit particles from left side
      if (timeRef.current % 2 === 0) {
        for (let i = 0; i < Math.ceil(2 + pressure * 4); i++) {
          const y = Math.random() * height;
          particles.push({
            x: 0,
            y: y,
            vx: 2 + pressure * 2,
            vy: (Math.random() - 0.5) * 0.5,
            life: 1,
          });
        }
      }

      // Update and render particles
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];

        // Fade out
        p.life -= 0.01;
        if (p.life <= 0) {
          particles.splice(i, 1);
          continue;
        }

        // Apply velocity
        p.x += p.vx;
        p.y += p.vy;

        // Wind shear effect
        p.vy += Math.sin(timeRef.current * 0.01 + p.y / 100) * 0.1 * pressure;

        // Collision with barriers
        for (const barrier of barriers) {
          if (
            p.x > barrier.x - 20 &&
            p.x < barrier.x + barrier.w + 20 &&
            p.y > barrier.y &&
            p.y < barrier.y + barrier.h
          ) {
            // Deflect around barrier
            const closestX = Math.max(barrier.x, Math.min(p.x, barrier.x + barrier.w));
            const closestY = Math.max(barrier.y, Math.min(p.y, barrier.y + barrier.h));

            const dx = p.x - closestX;
            const dy = p.y - closestY;
            const dist = Math.hypot(dx, dy);

            if (dist < 30) {
              const angle = Math.atan2(dy, dx);
              p.vx = Math.cos(angle) * 2;
              p.vy = Math.sin(angle) * 1.5;
              p.x += p.vx * 2;
              p.y += p.vy * 2;
            }
          }
        }

        // Remove if off screen
        if (p.x > width) {
          particles.splice(i, 1);
          continue;
        }

        // Draw particle with gradient
        const hue = 210 + (pressure * 60);
        const alpha = p.life * 0.6;
        ctx.fillStyle = `hsla(${hue}, 80%, 50%, ${alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.5 + pressure * 1.5, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw barriers
      ctx.fillStyle = "rgba(51, 65, 85, 0.4)";
      ctx.strokeStyle = "rgba(148, 163, 184, 0.2)";
      ctx.lineWidth = 1;
      for (const barrier of barriers) {
        ctx.fillRect(barrier.x, barrier.y, barrier.w, barrier.h);
        ctx.strokeRect(barrier.x, barrier.y, barrier.w, barrier.h);
      }

      // Draw flow lines showing pressure field
      if (pressure > 0.1) {
        ctx.strokeStyle = `rgba(139, 92, 246, ${0.05 * pressure})`;
        ctx.lineWidth = 0.5;
        const spacing = Math.ceil(20 / pressure);
        for (let y = 0; y < height; y += spacing) {
          ctx.beginPath();
          for (let x = 0; x < width; x += 10) {
            const waveOffset = Math.sin(x * 0.01 + timeRef.current * 0.02) * 10 * pressure;
            if (x === 0) {
              ctx.moveTo(x, y + waveOffset);
            } else {
              ctx.lineTo(x, y + waveOffset);
            }
          }
          ctx.stroke();
        }
      }

      // Info panel
      ctx.fillStyle = "rgba(15, 23, 42, 0.7)";
      ctx.strokeStyle = "rgba(148, 163, 184, 0.2)";
      ctx.lineWidth = 1;
      ctx.fillRect(10, 10, 240, 90);
      ctx.strokeRect(10, 10, 240, 90);

      ctx.fillStyle = "#e2e8f0";
      ctx.font = "bold 11px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("Wind Tunnel Dynamics", 18, 18);

      ctx.fillStyle = "rgba(226, 232, 240, 0.7)";
      ctx.font = "9px sans-serif";
      ctx.fillText(`Particle Flow: ${particles.length}`, 18, 35);
      ctx.fillText(`Pressure: ${intensity}%`, 18, 48);
      ctx.fillText(`Higher pressure = more turbulent flow`, 18, 61);
      ctx.fillText(`Bars deflect wind and keywords`, 18, 74);

      requestAnimationFrame(animate);
    };

    animate();
  }, [intensity]);

  return (
    <div className="space-y-4">
      <canvas
        ref={canvasRef}
        className="w-full h-96 rounded-lg bg-slate-900 border border-slate-700/50"
      />

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-300">
          Market Pressure: <span className="text-purple-400">{intensity}%</span>
        </label>
        <Slider
          value={[intensity]}
          onValueChange={([v]) => setIntensity(v)}
          min={10}
          max={100}
          step={5}
          className="w-full"
        />
        <p className="text-xs text-slate-500 mt-2">Wind represents keyword flow. Bars are competitor barriers. Increase pressure to see turbulent competition.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="bg-slate-800/40 rounded p-3 border border-slate-700/30">
          <div className="text-slate-400 text-xs">Active Particles</div>
          <div className="text-lg font-bold text-blue-400">
            {particlesRef.current.length}
          </div>
        </div>
        <div className="bg-slate-800/40 rounded p-3 border border-slate-700/30">
          <div className="text-slate-400 text-xs">Flow Intensity</div>
          <div className="text-lg font-bold text-purple-400">
            {(intensity * 0.5).toFixed(1)} m/s
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-400 bg-slate-900/50 rounded p-3 border border-slate-700/30">
        <p className="font-semibold text-slate-300 mb-2">Interpretation:</p>
        <ul className="space-y-1 text-slate-500">
          <li>• Blue particles = keywords flowing through market</li>
          <li>• Gray bars = competitors/barriers blocking keyword flow</li>
          <li>• Particle density = how saturated that market area is</li>
          <li>• Wind deflection patterns = where competition is strongest</li>
          <li>• Higher pressure = more aggressive keyword competition</li>
        </ul>
      </div>
    </div>
  );
}

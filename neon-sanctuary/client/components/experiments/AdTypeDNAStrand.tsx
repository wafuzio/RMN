import { useEffect, useRef } from "react";
import * as THREE from "three";

const generateDNAData = () => {
  const adTypes = ["Sponsored Brand", "Display", "Shoppable", "Video", "Native", "Carousel"];
  const retailers = ["Amazon", "Walmart", "Target", "Best Buy", "Costco", "Kroger"];

  return { adTypes, retailers };
};

export default function AdTypeDNAStrand() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const { adTypes, retailers } = generateDNAData();
    const width = containerRef.current.offsetWidth;
    const height = containerRef.current.offsetHeight;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);

    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
    camera.position.z = 8;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);

    sceneRef.current = scene;
    rendererRef.current = renderer;

    // Create helix
    const segments = 100;
    const radius = 2;
    const helixHeight = 10;

    // Create helix lines
    const helix1Points: THREE.Vector3[] = [];
    const helix2Points: THREE.Vector3[] = [];

    for (let i = 0; i < segments; i++) {
      const t = i / segments;
      const angle = t * Math.PI * 6;
      const y = (t - 0.5) * helixHeight;

      helix1Points.push(new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius));

      const angle2 = angle + Math.PI;
      helix2Points.push(new THREE.Vector3(Math.cos(angle2) * radius, y, Math.sin(angle2) * radius));
    }

    const helix1Geom = new THREE.BufferGeometry().setFromPoints(helix1Points);
    const helix2Geom = new THREE.BufferGeometry().setFromPoints(helix2Points);

    const helixMaterial = new THREE.LineBasicMaterial({ color: 0x8b5cf6, linewidth: 2 });
    const line1 = new THREE.Line(helix1Geom, helixMaterial);
    const line2 = new THREE.Line(helix2Geom, helixMaterial);

    scene.add(line1);
    scene.add(line2);

    // Create rungs
    const rungGeometry = new THREE.BufferGeometry();
    const rungPositions: number[] = [];

    const rungStep = Math.ceil(segments / 12);
    for (let i = 0; i < segments; i += rungStep) {
      const t = i / segments;
      const angle = t * Math.PI * 6;
      const y = (t - 0.5) * helixHeight;

      const x1 = Math.cos(angle) * radius;
      const z1 = Math.sin(angle) * radius;

      const angle2 = angle + Math.PI;
      const x2 = Math.cos(angle2) * radius;
      const z2 = Math.sin(angle2) * radius;

      rungPositions.push(x1, y, z1);
      rungPositions.push(x2, y, z2);
    }

    rungGeometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(rungPositions), 3));
    const rungMaterial = new THREE.LineBasicMaterial({ color: 0x3b82f6 });
    const rungs = new THREE.LineSegments(rungGeometry, rungMaterial);
    scene.add(rungs);

    // Add spheres at helix points
    const sphereGeometry = new THREE.SphereGeometry(0.15, 8, 8);
    const sphereMaterial = new THREE.MeshBasicMaterial({ color: 0x3b82f6 });

    const sphereStep = Math.ceil(segments / 20);
    for (let i = 0; i < segments; i += sphereStep) {
      const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
      const t = i / segments;
      const angle = t * Math.PI * 6;
      const y = (t - 0.5) * helixHeight;

      sphere.position.set(Math.cos(angle) * radius, y, Math.sin(angle) * radius);
      scene.add(sphere);
    }

    // Lighting
    const light = new THREE.PointLight(0xffffff, 1, 100);
    light.position.set(5, 5, 5);
    scene.add(light);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    // Animation loop
    const animate = () => {
      requestAnimationFrame(animate);

      line1.rotation.y += 0.004;
      line2.rotation.y += 0.004;
      rungs.rotation.y += 0.004;

      renderer.render(scene, camera);
    };

    animate();

    // Handle resize
    const handleResize = () => {
      if (!containerRef.current) return;
      const newWidth = containerRef.current.offsetWidth;
      const newHeight = containerRef.current.offsetHeight;

      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (rendererRef.current && containerRef.current) {
        try {
          containerRef.current.removeChild(renderer.domElement);
        } catch {
          // Already removed
        }
      }
      renderer.dispose();
    };
  }, []);

  return (
    <div className="space-y-4">
      <div
        ref={containerRef}
        className="w-full h-96 rounded-lg bg-gradient-to-br from-slate-700/50 to-slate-800/50 border border-slate-600/50 overflow-hidden"
      />
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Ad Types</div>
          <div className="text-lg font-bold text-blue-400">6</div>
        </div>
        <div className="bg-slate-700/30 rounded p-3 border border-slate-600/50">
          <div className="text-slate-400">Retailers</div>
          <div className="text-lg font-bold text-purple-400">6</div>
        </div>
      </div>
      <div className="text-xs text-slate-500">
        Left helix: Ad Types | Right helix: Retailers | Rungs: Frequency relationships
      </div>
    </div>
  );
}

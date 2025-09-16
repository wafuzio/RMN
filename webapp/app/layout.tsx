export const metadata = { title: 'Kroger Webapp', description: 'Next.js rebuild' };
import '../styles/globals.css';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

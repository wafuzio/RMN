// Extend React's JSX types with spec-compliant HTML attributes
import 'react';

declare module 'react' {
  // Extend React's intrinsic img attributes with the fetchpriority attribute
  interface ImgHTMLAttributes<T> {
    fetchpriority?: 'high' | 'low' | 'auto';
  }
}

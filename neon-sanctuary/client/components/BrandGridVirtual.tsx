import React, { useCallback } from 'react';
import { BrandLogo } from '@/components/dashboard/BrandLogo';

// Direct require for CommonJS module (react-window v1.x)
const { FixedSizeGrid: Grid } = require('react-window');

type Brand = { brand: string; logo?: string; slug?: string; count?: number };

export function BrandGridVirtual({
  items,
  onOpen,
  onHover,
  width = 1024,
  height = 640,
  columnWidth = 200,
  rowHeight = 240,
}: {
  items: Brand[];
  onOpen: (b: Brand) => void;
  onHover?: (b: Brand) => void;
  width?: number;
  height?: number;
  columnWidth?: number;
  rowHeight?: number;
}) {
  const columns = Math.max(1, Math.floor(width / columnWidth));
  const rows = Math.ceil(items.length / columns);

  const Cell = useCallback(({ columnIndex, rowIndex, style }: any) => {
    const i = rowIndex * columns + columnIndex;
    if (i >= items.length) return null;
    const b = items[i];
    return (
      <div style={{ ...style, padding: 12 }}>
        <button
          className="group bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 p-3 flex flex-col items-center justify-center gap-2 cursor-pointer hover:scale-105 w-full h-full"
          onClick={() => onOpen(b)}
          onMouseEnter={() => onHover?.(b)}
        >
          <div className="flex items-center justify-center h-36 w-36 flex-shrink-0 group-hover:scale-110 transition-transform duration-200">
            <BrandLogo brand={b.brand} className="h-30 w-30" />
          </div>
          <div className="text-center space-y-1">
            <p className="font-bold text-gray-900 text-sm line-clamp-2 group-hover:text-blue-600 transition-colors">
              {b.brand}
            </p>
            {typeof b.count === 'number' && (
              <p className="text-xs text-gray-500">{b.count} ads</p>
            )}
          </div>
        </button>
      </div>
    );
  }, [items, columns, onOpen, onHover]);

  return (
    <Grid
      columnCount={columns}
      columnWidth={columnWidth}
      height={height}
      rowCount={rows}
      rowHeight={rowHeight}
      width={width}
    >
      {Cell}
    </Grid>
  );
}

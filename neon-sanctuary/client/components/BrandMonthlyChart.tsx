import React from 'react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip
} from 'recharts';

export default function BrandMonthlyChart({ 
  data 
}: { 
  data: Array<{ month: string; count: number }> 
}) {
  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="count" fill="#6366f1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

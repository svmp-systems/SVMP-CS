"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const colors = ["#2F6B57", "#A33D55", "#7FA36A", "#D5E271", "#151915"];

export function AutomationTrendChart({
  data,
}: {
  data: Array<{ day: string; answered: number; escalated: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ left: -20, right: 12, top: 10, bottom: 0 }}>
          <CartesianGrid stroke="#D8DED8" strokeDasharray="3 3" />
          <XAxis dataKey="day" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} />
          <Tooltip />
          <Area type="monotone" dataKey="answered" stackId="1" stroke="#2F6B57" fill="#2F6B57" fillOpacity={0.22} />
          <Area type="monotone" dataKey="escalated" stackId="1" stroke="#A33D55" fill="#A33D55" fillOpacity={0.18} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TopicPieChart({
  data,
}: {
  data: Array<{ name: string; value: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} innerRadius={58} outerRadius={96} dataKey="value" nameKey="name" paddingAngle={3}>
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ResponseTimeChart({
  data,
}: {
  data: Array<{ hour: string; minutes: number }>;
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: -20, right: 12, top: 10, bottom: 0 }}>
          <CartesianGrid stroke="#D8DED8" strokeDasharray="3 3" />
          <XAxis dataKey="hour" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} />
          <Tooltip />
          <Bar dataKey="minutes" radius={[6, 6, 0, 0]} fill="#2F6B57" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

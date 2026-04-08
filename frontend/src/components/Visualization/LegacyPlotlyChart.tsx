import React, { Suspense } from 'react';

const Plot = React.lazy(() => import('react-plotly.js'));

interface LegacyPlotlyChartProps {
  spec: any;
}

const LegacyPlotlyChart: React.FC<LegacyPlotlyChartProps> = ({ spec }) => {
  return (
    <div className="w-full card-apple p-6 my-4">
      <Suspense fallback={<div className="h-64 flex items-center justify-center text-apple-gray-500">Loading chart…</div>}>
        <Plot
          data={spec.data}
          layout={{
            ...spec.layout,
            autosize: true,
            responsive: true,
            font: {
              family: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", Inter, system-ui, sans-serif',
              color: '#1C1C1E',
            },
            paper_bgcolor: 'rgba(255, 253, 249, 0)',
            plot_bgcolor: 'rgba(255, 253, 249, 0)',
            colorway: ['#C2581C', '#2D7A6F', '#D4794D', '#246359', '#8C7B6B', '#A30046', '#D4001A', '#002B5C'],
          }}
          config={{
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'] as any,
          }}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler={true}
        />
      </Suspense>
    </div>
  );
};

export default LegacyPlotlyChart;

import Plot from 'react-plotly.js';

interface ChartRendererProps {
  spec: any;
}

const ChartRenderer: React.FC<ChartRendererProps> = ({ spec }) => {
  if (!spec || !spec.data) {
    return null;
  }

  return (
    <div className="w-full card-apple p-6 my-4">
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
          paper_bgcolor: 'rgba(255, 255, 255, 0)',
          plot_bgcolor: 'rgba(255, 255, 255, 0)',
          colorway: ['#007AFF', '#34C759', '#FF9500', '#FF3B30', '#5E5CE6', '#AF52DE', '#FF2D55', '#5AC8FA'],
        }}
        config={{
          responsive: true,
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
};

export default ChartRenderer;

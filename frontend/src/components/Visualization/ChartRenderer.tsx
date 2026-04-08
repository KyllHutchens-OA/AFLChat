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
          paper_bgcolor: 'rgba(255, 253, 249, 0)',
          plot_bgcolor: 'rgba(255, 253, 249, 0)',
          colorway: ['#C2581C', '#2D7A6F', '#D4794D', '#246359', '#8C7B6B', '#A30046', '#D4001A', '#002B5C'],
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

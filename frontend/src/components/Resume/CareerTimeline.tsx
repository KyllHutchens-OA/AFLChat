import Plot from 'react-plotly.js';

interface TimelineItem {
  company: string;
  title: string;
  start_date: string;
  end_date: string;
  type: 'work' | 'education';
  highlight?: string;
}

interface CareerTimelineProps {
  items: TimelineItem[];
}

const CareerTimeline: React.FC<CareerTimelineProps> = ({ items }) => {
  // Single color scheme - blue for work, purple for education
  const getColor = (type: string) => type === 'education' ? '#8b5cf6' : '#3b82f6';

  // Prepare data for timeline
  const data = items.map((item, index) => {
    const startDate = new Date(item.start_date);
    const endDate = item.end_date === 'Present' ? new Date() : new Date(item.end_date);
    const color = getColor(item.type);

    // Build hover text with highlight if available
    let hoverText = `<b>${item.title}</b><br>${item.company}<br>${item.start_date} - ${item.end_date}`;
    if (item.highlight) {
      hoverText += `<br><br><i>${item.highlight}</i>`;
    }

    return {
      x: [startDate, endDate],
      y: [index, index],
      mode: 'lines' as const,
      line: {
        color: color,
        width: 24,
      },
      name: item.company,
      hoverinfo: 'text' as const,
      hovertext: hoverText,
    };
  });

  // Add markers for start points
  const markers = {
    x: items.map((item) => new Date(item.start_date)),
    y: items.map((_, index) => index),
    mode: 'markers' as const,
    marker: {
      size: 10,
      color: '#fff',
      line: {
        color: items.map((item) => getColor(item.type)),
        width: 2,
      },
    },
    hoverinfo: 'skip' as const,
    showlegend: false,
  };

  const layout = {
    title: {
      text: 'Career Timeline',
      font: { size: 16, color: '#1f2937' },
    },
    showlegend: false,
    xaxis: {
      title: '',
      showgrid: true,
      gridcolor: '#e5e7eb',
      tickformat: '%Y',
    },
    yaxis: {
      title: '',
      showgrid: false,
      tickmode: 'array' as const,
      tickvals: items.map((_, index) => index),
      ticktext: items.map((item) =>
        `${item.title}<br><span style="font-size:10px;color:#6b7280">${item.company}</span>`
      ),
      automargin: true,
    },
    height: Math.max(220, items.length * 55 + 100),
    margin: { l: 220, r: 40, t: 60, b: 40 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    hovermode: 'closest' as const,
  };

  const config = {
    displayModeBar: false,
    responsive: true,
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <Plot
        data={[...data, markers]}
        layout={layout}
        config={config}
        style={{ width: '100%' }}
      />
      {/* Simple legend */}
      <div className="flex justify-center gap-6 mt-2">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span className="text-xs text-gray-600">Work Experience</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-purple-500" />
          <span className="text-xs text-gray-600">Education</span>
        </div>
      </div>
    </div>
  );
};

export default CareerTimeline;

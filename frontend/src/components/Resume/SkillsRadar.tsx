import Plot from 'react-plotly.js';

interface SkillsRadarProps {
  skills: Record<string, number>; // skill name -> proficiency (1-5)
}

const SkillsRadar: React.FC<SkillsRadarProps> = ({ skills }) => {
  const skillNames = Object.keys(skills);
  const skillValues = Object.values(skills);

  // Close the radar chart by repeating the first value
  const closedValues = [...skillValues, skillValues[0]];
  const closedNames = [...skillNames, skillNames[0]];

  const data = [
    {
      type: 'scatterpolar' as const,
      r: closedValues,
      theta: closedNames,
      fill: 'toself' as const,
      fillcolor: 'rgba(59, 130, 246, 0.2)',
      line: {
        color: '#3b82f6',
        width: 2,
      },
      marker: {
        size: 6,
        color: '#3b82f6',
      },
      name: 'Skills',
      hovertemplate: '<b>%{theta}</b><br>Proficiency: %{r}/5<extra></extra>',
    },
  ];

  const layout = {
    title: {
      text: 'Skills Overview',
      font: { size: 16, color: '#1f2937' },
    },
    polar: {
      radialaxis: {
        visible: true,
        range: [0, 5],
        tickvals: [1, 2, 3, 4, 5],
        ticktext: ['1', '2', '3', '4', '5'],
        tickfont: { size: 10, color: '#6b7280' },
        gridcolor: '#e5e7eb',
        linecolor: '#e5e7eb',
      },
      angularaxis: {
        tickfont: { size: 11, color: '#374151' },
        gridcolor: '#e5e7eb',
        linecolor: '#e5e7eb',
      },
      bgcolor: 'rgba(0,0,0,0)',
    },
    showlegend: false,
    height: 350,
    margin: { l: 60, r: 60, t: 60, b: 40 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
  };

  const config = {
    displayModeBar: false,
    responsive: true,
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={{ width: '100%' }}
      />
      {/* Proficiency Legend */}
      <div className="flex justify-center gap-4 mt-2 text-xs text-gray-500">
        <span>1 = Basic</span>
        <span>3 = Proficient</span>
        <span>5 = Expert</span>
      </div>
    </div>
  );
};

export default SkillsRadar;

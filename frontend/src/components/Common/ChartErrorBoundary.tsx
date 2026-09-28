import React from 'react';
import DataTable from '../Visualization/DataTable';

interface ChartErrorBoundaryProps {
  children: React.ReactNode;
  // Raw chart data, if available, so the fallback can render a table instead
  // of just an error message.
  data?: Record<string, unknown>[] | null;
  title?: string;
}

interface ChartErrorBoundaryState {
  hasError: boolean;
}

/**
 * Catches render-time errors thrown by ChartRenderer (and anything it renders,
 * e.g. Recharts choking on an unexpected spec shape). Before this existed there
 * were zero error boundaries in the app, so a single bad chart spec would
 * white-screen the entire page.
 */
class ChartErrorBoundary extends React.Component<ChartErrorBoundaryProps, ChartErrorBoundaryState> {
  constructor(props: ChartErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ChartErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('ChartErrorBoundary caught a chart rendering error:', error, errorInfo);
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      if (this.props.data && this.props.data.length > 0) {
        return <DataTable data={this.props.data} title={this.props.title} />;
      }
      return (
        <div className="w-full text-center text-sm text-warm-700 py-2">
          Chart failed to render.
        </div>
      );
    }

    return this.props.children;
  }
}

export default ChartErrorBoundary;

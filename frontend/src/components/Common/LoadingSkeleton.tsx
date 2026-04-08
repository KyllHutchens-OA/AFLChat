interface LoadingSkeletonProps {
  lines?: number;
  height?: string;
  variant?: 'text' | 'card' | 'chart';
}

const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ lines = 3, height, variant = 'text' }) => {
  if (variant === 'card') {
    return (
      <div className="animate-shimmer rounded-lg" style={{ height: height || '200px' }} />
    );
  }

  if (variant === 'chart') {
    return (
      <div className="space-y-3">
        <div className="animate-shimmer rounded-lg h-8 w-1/3" />
        <div className="animate-shimmer rounded-lg" style={{ height: height || '300px' }} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="animate-shimmer rounded h-4"
          style={{ width: i === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  );
};

export default LoadingSkeleton;

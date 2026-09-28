interface EmptyStateProps {
  icon?: string;
  headline: string;
  subtext?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

const EmptyState: React.FC<EmptyStateProps> = ({ icon, headline, subtext, action }) => {
  return (
    <div className="card p-8 text-center">
      {icon && <div className="text-5xl mb-4">{icon}</div>}
      <h2 className="text-2xl font-semibold text-warm-900 mb-2">{headline}</h2>
      {subtext && <p className="text-warm-500 mb-4">{subtext}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="btn-primary"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};

export default EmptyState;

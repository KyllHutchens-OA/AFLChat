import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChartRenderer from '../Visualization/ChartRenderer';

interface ResponseCardProps {
  text: string;
  visualization?: any;
  isError?: boolean;
}

const ResponseCard: React.FC<ResponseCardProps> = ({ text, visualization, isError }) => {
  if (isError) {
    return (
      <div className="card-apple border-l-4 border-l-red-400 p-5">
        <div className="flex items-center gap-2 mb-2 text-red-600">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">Something went wrong</span>
        </div>
        <div className="chat-markdown text-afl-warm-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div className="card-apple p-5 animate-fade-in">
      <div className="chat-markdown text-afl-warm-900">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
      {visualization && (
        <>
          <div className="border-t border-afl-warm-100 my-4" />
          <ChartRenderer spec={visualization} />
        </>
      )}
    </div>
  );
};

export default ResponseCard;

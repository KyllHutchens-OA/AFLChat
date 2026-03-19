import { useState } from 'react';

interface FeedbackButtonProps {
  conversationId: string | null;
  messageText: string;
}

const FeedbackButton: React.FC<FeedbackButtonProps> = ({ conversationId, messageText }) => {
  const [showThanks, setShowThanks] = useState(false);

  const handleFeedback = () => {
    // Build GitHub issue URL with pre-populated context
    const issueTitle = encodeURIComponent('Feedback: Unexpected AI response');

    // Truncate message for URL (keep first 500 chars)
    const truncatedMessage = messageText.length > 500
      ? messageText.substring(0, 500) + '...'
      : messageText;

    const issueBody = encodeURIComponent(
      `## What happened?\n\n[Please describe what was wrong with the response]\n\n` +
      `## Response received:\n\`\`\`\n${truncatedMessage}\n\`\`\`\n\n` +
      `## Conversation link:\n${conversationId ? `${window.location.origin}/aflagent/${conversationId}` : 'New conversation (no ID yet)'}\n\n` +
      `## Additional context:\n- Time: ${new Date().toISOString()}\n- URL: ${window.location.href}`
    );

    const githubUrl = `https://github.com/KyllHutchens-OA/AFLChat/issues/new?title=${issueTitle}&body=${issueBody}&labels=ai-feedback`;

    window.open(githubUrl, '_blank');
    setShowThanks(true);

    // Reset after 3 seconds
    setTimeout(() => setShowThanks(false), 3000);
  };

  if (showThanks) {
    return (
      <div className="mt-3 text-center">
        <p className="text-sm text-apple-green flex items-center justify-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Thanks for helping AFL.NAC improve!
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 text-center">
      <p className="text-xs text-apple-gray-500 mb-1">
        AFL.NAC is still learning. If this response seems off, wrong, or just plain weird, let us know and we'll work to fix it!
      </p>
      <button
        onClick={handleFeedback}
        className="text-xs text-apple-blue-500 hover:text-apple-blue-600 inline-flex items-center gap-1 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
        </svg>
        Report an issue
      </button>
    </div>
  );
};

export default FeedbackButton;

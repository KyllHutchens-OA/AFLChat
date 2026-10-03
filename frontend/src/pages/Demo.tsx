import { useNavigate } from 'react-router-dom';

// 30-second product demo (rendered with HyperFrames from real captures, see demo/).
const Demo = () => {
  const navigate = useNavigate();

  return (
    <section className="bg-paper paper-grain min-h-full">
      <div className="max-w-5xl mx-auto px-4 sm:px-8 lg:px-10 py-10 sm:py-16">
        <h1 className="font-display text-4xl sm:text-5xl text-ink mb-3">See it in 30 seconds.</h1>
        <p className="text-lg text-warm-700 mb-8 max-w-2xl">
          Ask a question in plain English and get the answer with a chart. Then follow a game quarter
          by quarter on the live page.
        </p>

        <div className="rounded-xl overflow-hidden shadow-card-lg bg-ink">
          <video
            className="w-full h-auto block"
            src="/media/footy-nac-demo.mp4"
            poster="/media/footy-nac-demo.jpg"
            autoPlay
            muted
            loop
            playsInline
            controls
            preload="metadata"
            aria-label="Footy-NAC demo: asking a question, then the live game view"
          />
        </div>

        <div className="flex flex-wrap gap-3 mt-8">
          <button onClick={() => navigate('/ask')} className="btn-primary">
            Ask a question
          </button>
          <button onClick={() => navigate('/live')} className="btn-secondary">
            Go to Live
          </button>
        </div>
      </div>
    </section>
  );
};

export default Demo;

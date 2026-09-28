import { useNavigate } from 'react-router-dom';
import landingProof from '../../data/landingProof.json';
import Sparkline from './Sparkline';
import MiniQuarterChart from './MiniQuarterChart';

const ProofCards = () => {
  const navigate = useNavigate();
  const ask = (q: string) => navigate(`/ask?q=${encodeURIComponent(q)}`);
  const { goalkicker, headToHead } = landingProof;

  return (
    <section className="bg-paper py-14 sm:py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
        <h2 className="font-display text-3xl text-ink mb-2">What can it do?</h2>
        <p className="text-warm-600 mb-8 max-w-2xl">
          Real outputs from the app, not mock-ups. Answered from 7,090 matches and 299,975 player-game
          rows.
        </p>

        <div className="grid md:grid-cols-3 gap-5">
          {/* Card 1: records and trivia */}
          <div className="card p-6 flex flex-col">
            <span className="section-label mb-2">Records &amp; trivia</span>
            <p className="text-ink font-medium mb-3">&ldquo;{goalkicker.question}&rdquo;</p>
            <p className="text-sm text-warm-700 mb-4">{goalkicker.answer}</p>
            <div className="mb-4">
              <Sparkline values={goalkicker.bySeason} color="#C8102E" />
            </div>
            <div className="mt-auto flex items-center justify-between">
              <button onClick={() => ask(goalkicker.askQuestion)} className="btn-secondary text-sm py-2 px-4">
                Ask this
              </button>
              <span className="text-xs text-warm-600">299,975 player-game rows</span>
            </div>
          </div>

          {/* Card 2: head to head */}
          <div className="card p-6 flex flex-col">
            <span className="section-label mb-2">Head to head</span>
            <p className="text-ink font-medium mb-3">&ldquo;{headToHead.question}&rdquo;</p>
            <p className="text-sm text-warm-700 mb-4">{headToHead.answer}</p>
            <div className="mb-4">
              <MiniQuarterChart
                home={{ quarters: headToHead.daicos.values, primary: headToHead.daicos.primary }}
                away={{ quarters: headToHead.bontempelli.values, primary: headToHead.bontempelli.primary }}
              />
            </div>
            <div className="mt-auto flex items-center justify-between">
              <button onClick={() => ask(headToHead.askQuestion)} className="btn-secondary text-sm py-2 px-4">
                Ask this
              </button>
              <span className="text-xs text-warm-600">Here's the SQL, too</span>
            </div>
          </div>

          {/* Card 3: live footy */}
          <div className="card p-6 flex flex-col">
            <span className="section-label mb-2">Live footy</span>
            <p className="text-ink font-medium mb-3">&ldquo;How did the Grand Final play out, quarter by quarter?&rdquo;</p>
            <p className="text-sm text-warm-700 mb-4">
              Quarter-by-quarter scoring, an AI summary per quarter, and scoring pops as they happen.
            </p>
            <div className="mb-4">
              <MiniQuarterChart
                home={{ quarters: [22, 43, 72, 89], primary: '#2A0D45' }}
                away={{ quarters: [23, 43, 62, 96], primary: '#A30046' }}
              />
            </div>
            <div className="mt-auto flex items-center justify-between">
              <button onClick={() => ask('How did the 2026 Grand Final play out quarter by quarter?')} className="btn-secondary text-sm py-2 px-4">
                Ask this
              </button>
              <button onClick={() => navigate('/live')} className="text-xs text-sherrin hover:underline">
                Or see it live &rarr;
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProofCards;

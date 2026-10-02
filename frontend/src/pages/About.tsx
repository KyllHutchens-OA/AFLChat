import HowItThinks from '../components/Landing/HowItThinks';
import LandingFooter from '../components/Landing/LandingFooter';

// "How it works": the honest, technical-audience version of About. The
// pipeline diagram and real numbers are the same HowItThinks component used
// on the landing page, so the promise made there and the explanation here
// are exactly the same artefact, not a rewritten claim.
const About = () => {
  return (
    <div>
      <div className="max-w-3xl mx-auto px-6 sm:px-8 lg:px-10 py-12 sm:py-16">
        <h1 className="font-display text-4xl sm:text-5xl text-ink mb-4">How it works.</h1>
        <p className="text-lg text-warm-700 mb-4">
          Footy-NAC answers questions about the AFL: who has kicked the most goals since 1990, which
          game had the most handballs, how close the 2025 finals were. Type a question in plain English.
          It becomes a SQL query against 36 years of match and player data, gets checked before you see
          it, and comes back with a chart when one helps.
        </p>
        <p className="text-warm-700 mb-4">
          It also has a live scores view for footy days, with quarter-by-quarter breakdowns and an AI
          summary, so you don't need five tabs open to follow a game.
        </p>
        <p className="text-warm-700">
          I'm a data scientist who wanted footy debates settled with numbers. Below is the real
          pipeline. Hover a step to see the output from a stored answer.
        </p>
      </div>

      <HowItThinks />

      <div className="max-w-3xl mx-auto px-6 sm:px-8 lg:px-10 py-10 text-center">
        <p className="text-warm-700">
          Built solo, evaluated on ground-truth cases before anything ships. If you find a wrong answer,
          there's a report button on every response in chat.
        </p>
      </div>

      <LandingFooter />
    </div>
  );
};

export default About;
